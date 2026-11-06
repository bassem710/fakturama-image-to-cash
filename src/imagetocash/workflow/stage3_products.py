"""Stage 3 (spec 3.1-3.17): for every item, in source order, select or create the Product."""

from __future__ import annotations

from imagetocash.domain.matching import PRODUCT_MATCH_POLICY, VAT_MATCH_POLICY, normalize_text, vat_name_for
from imagetocash.domain.models import LineItem
from imagetocash.domain.pricing import gross_master_price
from imagetocash.domain.review import ManualReviewRequired, ReviewReason
from imagetocash.workflow.checks import check_item_line
from imagetocash.workflow.context import RunContext
from imagetocash.workflow.protocols import FakturamaUi, Row
from imagetocash.workflow.resolver import decide, require_exact

STANDARD_RATE_CODE = "S"


class ProductsStage:
    def __init__(self, ui: FakturamaUi) -> None:
        self._ui = ui
        self._product_policy = PRODUCT_MATCH_POLICY.ocr_tolerant()
        self._vat_policy = VAT_MATCH_POLICY.ocr_tolerant()

    def run(self, ctx: RunContext) -> None:
        with ctx.evidence.spec_step("3.1", f"Process {len(ctx.order.items)} item(s) in source order"):
            pass
        for line_index, item in enumerate(ctx.order.items):
            self._process_item(ctx, line_index, item)

        with ctx.evidence.spec_step("3.17", "Every source item has its line on the Order") as rec:
            lines = self._ui.order.read_item_lines()
            rec.observed = f"{len(lines)} line(s)"
            if len(lines) != len(ctx.order.items):
                raise ManualReviewRequired(
                    "3.17",
                    ReviewReason.VALUE_MISMATCH,
                    f"{len(lines)} lines on screen, {len(ctx.order.items)} on image",
                )

    def _process_item(self, ctx: RunContext, line_index: int, item: LineItem) -> None:
        ev, order_ui = ctx.evidence, self._ui.order
        wanted = {"sku": item.sku}

        with ev.spec_step("3.2", f"[{item.sku}] Open Select a product (upper icon beside Items)"):
            order_ui.activate()
            dialog = order_ui.open_product_selector()

        with ev.spec_step("3.3", f"[{item.sku}] Search the exact SKU") as rec:
            row = decide(self._product_policy, wanted, dialog.search(item.sku), "3.3")
            if row is None:
                dialog.cancel()
                rec.observed = "no exact SKU -> Cancel, create the Product"
            else:
                dialog.choose(row)
                rec.observed = "exact SKU selected -> OK"

        if row is None:
            row = self._create_product(ctx, item)
        ctx.product_rows[item.sku] = row
        self._complete_line(ctx, line_index, item)

    def _create_product(self, ctx: RunContext, item: LineItem) -> Row:
        ev, ui = ctx.evidence, self._ui
        vat_name = vat_name_for(item.vat_percent)
        wanted_vat = {"name": vat_name, "value": str(item.vat_percent), "code": STANDARD_RATE_CODE}

        with ev.spec_step("3.4", f"[{item.sku}] Data > VATs: search {vat_name}") as rec:
            ui.vats.open()
            rows = ui.vats.search(vat_name)
            rec.observed = f"{len(rows)} row(s)"

        with ev.spec_step("3.5", f"[{item.sku}] Reuse only Name/Value/code S exact") as rec:
            existing_vat = decide(self._vat_policy, wanted_vat, rows, "3.5")
            rec.observed = "reuse existing VAT" if existing_vat else "missing -> create (3.6)"

        if existing_vat is None:
            with ev.spec_step("3.6", f"[{item.sku}] Create {vat_name} (code S, value {item.vat_percent}), save once"):
                ui.vats.create_new()
                ui.vat_editor.fill(vat_name, item.vat_percent)
                ui.vat_editor.save()  # waits until saved; 3.7 then proves it via the Product's VAT dropdown

        with ev.spec_step("3.7", f"[{item.sku}] New product (VAT now in the dropdown)") as rec:
            ui.product_editor.open_new_product()
            options = ui.product_editor.vat_options()
            rec.observed = ", ".join(options)
            if not any(normalize_text(o) == normalize_text(vat_name) for o in options):
                raise ManualReviewRequired("3.7", ReviewReason.UI_ELEMENT_NOT_FOUND, f"{vat_name} not in VAT dropdown")

        gross = gross_master_price(item.unit_net_price, item.vat_percent)
        with (
            ev.spec_step("3.8", f"[{item.sku}] Item Number, Name, Description"),
            ev.spec_step("3.9", f"[{item.sku}] Price (gross)", expected=str(gross)),
            ev.spec_step("3.10", f"[{item.sku}] cost price 0.00, VAT {vat_name}, Stock 0.00"),
        ):
            ui.product_editor.fill(item, gross, vat_name)

        with ev.spec_step("3.11", f"[{item.sku}] Save the Product once"):
            ui.product_editor.save()

        with ev.spec_step("3.12", f"[{item.sku}] Back on the Order: select the new Product") as rec:
            ui.order.activate()
            dialog = ui.order.open_product_selector()
            row = require_exact(self._product_policy, {"sku": item.sku}, dialog.search(item.sku), "3.12")
            dialog.choose(row)
            rec.observed = "new Product selected"
        return row

    def _complete_line(self, ctx: RunContext, line_index: int, item: LineItem) -> None:
        ev, order_ui = ctx.evidence, self._ui.order
        with (
            ev.spec_step("3.13", f"[{item.sku}] Qty.", expected=str(item.quantity)),
            ev.spec_step(
                "3.14", f"[{item.sku}] U.Price / VAT", expected=f"{item.unit_net_price} / {item.vat_percent}%"
            ),
            ev.spec_step("3.15", f"[{item.sku}] Discount", expected=f"{item.discount_percent}%"),
        ):
            order_ui.fill_item_line(line_index, item)

        with ev.spec_step("3.16", f"[{item.sku}] Line Price = qty x net x (1 - disc)") as rec:
            lines = order_ui.read_item_lines()
            if line_index >= len(lines):
                raise ManualReviewRequired("3.16", ReviewReason.VALUE_MISMATCH, f"line {line_index + 1} not on screen")
            check_item_line(lines[line_index], item, "3.16")
            rec.observed = lines[line_index].get("price", "")
