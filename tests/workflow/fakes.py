"""An in-memory Fakturama that implements every workflow protocol. Used to test the spec logic
(select / create-then-reselect / stop) without the real application."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from imagetocash.domain.matching import normalize_text
from imagetocash.domain.models import Debtor, LineItem
from imagetocash.domain.pricing import line_net_price, round_money, vat_amount


@dataclass
class FakeDb:
    debtors: list[dict[str, str]] = field(default_factory=list)
    products: list[dict[str, str]] = field(default_factory=list)
    vats: list[dict[str, str]] = field(default_factory=list)
    payment_methods: list[dict[str, str]] = field(default_factory=list)
    documents: list[dict[str, str]] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)


def _contains(haystack: str, needle: str) -> bool:
    return normalize_text(needle) in normalize_text(haystack)


class FakeSelectionDialog:
    def __init__(
        self, rows: list[dict[str, str]], key: str, on_choose, db: FakeDb, name: str, *, auto_apply: bool = False
    ) -> None:
        self._rows, self._key, self._on_choose, self._db, self._name = rows, key, on_choose, db, name
        self._auto_apply, self.auto_applied = auto_apply, False

    def search(self, text: str) -> list[dict[str, str]]:
        self._db.calls.append(f"{self._name}.search:{text}")
        hits = [dict(r) for r in self._rows if any(_contains(v, text) for v in r.values())]
        if self._auto_apply and len(hits) == 1:  # like Fakturama's 'Select a product': applies, closes
            self.auto_applied = True
            self._on_choose(hits[0])
            return []
        return [r for r in hits if _contains(r.get(self._key, ""), text)]

    def choose(self, row) -> None:
        self._db.calls.append(f"{self._name}.choose")
        self._on_choose(row)

    def cancel(self) -> None:
        self._db.calls.append(f"{self._name}.cancel")


class FakeOrderEditor:
    def __init__(self, db: FakeDb) -> None:
        self.db = db
        self.number = ""
        self.fields: dict[str, str] = {}
        self.debtor: dict[str, str] | None = None
        self.lines: list[dict[str, str]] = []
        self.saved = False

    def open_new_order(self) -> None:
        orders = [d for d in self.db.documents if d["type"] == "Order"]
        self.number = f"PO{len(orders) + 1:06d}"
        self.fields = {"vat_mode": "With VAT", "price_mode": "Gross"}
        self.debtor, self.lines, self.saved = None, [], False

    def activate(self) -> None:
        self.db.calls.append("order.activate")

    def read_document_number(self) -> str:
        return self.number

    def set_order_date(self, value: date) -> None:
        self.fields["date"] = value.isoformat()

    def set_customer_reference(self, value: str) -> None:
        self.fields["reference"] = value

    def set_price_mode_net(self) -> None:
        self.fields["price_mode"] = "Net"

    def read_vat_mode(self) -> str:
        return self.fields["vat_mode"]

    def open_address_selector(self) -> FakeSelectionDialog:
        def choose(row) -> None:
            self.debtor = row

        return FakeSelectionDialog(self.db.debtors, "company", choose, self.db, "address_dialog")

    def read_address_texts(self) -> dict[str, str]:
        assert self.debtor is not None
        return {"invoice": self.debtor["invoice_text"], "delivery": self.debtor["delivery_text"]}

    def open_product_selector(self) -> FakeSelectionDialog:
        def choose(row) -> None:
            vat = Decimal(row["vat"].rstrip("%"))
            net = round_money(Decimal(row["gross"]) / (1 + vat / 100))
            self.lines.append(
                {
                    "sku": row["sku"],
                    "quantity": "1",
                    "unit_price": str(net),
                    "vat": row["vat"],
                    "discount": "0%",
                    "price": str(net),
                }
            )

        return FakeSelectionDialog(self.db.products, "sku", choose, self.db, "product_dialog", auto_apply=True)

    def read_item_lines(self) -> list[dict[str, str]]:
        return [dict(line) for line in self.lines]

    def fill_item_line(self, line_index: int, item: LineItem) -> None:
        line = self.lines[line_index]
        line.update(
            quantity=str(item.quantity), unit_price=str(item.unit_net_price), discount=f"{item.discount_percent}%"
        )
        line["price"] = str(line_net_price(item.quantity, item.unit_net_price, item.discount_percent))

    def ensure_order_level_defaults(self) -> None:
        self.fields.update(discount="0%", shipping="0.00")

    def read_totals(self) -> dict[str, str]:
        net = sum((Decimal(line["price"]) for line in self.lines), Decimal(0))
        vat = sum(
            (vat_amount(Decimal(line["price"]), Decimal(line["vat"].rstrip("%"))) for line in self.lines), Decimal(0)
        )
        return {"net": f"${net}", "vat": f"${vat}", "total": f"${net + vat}"}

    def save(self) -> None:
        self.db.calls.append("order.save")
        self.saved = True
        self.db.documents.append(
            {
                "type": "Order",
                "number": self.number,
                "date": self.fields["date"],
                "reference": self.fields["reference"],
                "state": "open",
                "total": self.read_totals()["total"],
            }
        )

    def create_follow_up_invoice(self) -> None:
        self.db.calls.append("order.follow_up_invoice")


class FakeDebtorEditor:
    def __init__(self, db: FakeDb) -> None:
        self.db = db
        self.draft: dict[str, str] = {}

    def open_new_debtor(self) -> None:
        self.db.calls.append("debtor.new")
        self.draft = {}

    def fill_identity(self, debtor: Debtor) -> None:
        self.draft.update(company=debtor.company, first_name=debtor.first_name, last_name=debtor.last_name)

    def fill_main_address(self, debtor: Debtor) -> None:
        a = debtor.billing_address
        self.draft.update(zip=a.zip_code, city=a.city, invoice_text=f"{a.name}\n{a.street}\n{a.zip_code} {a.city}")

    def assign_address_roles(self, debtor: Debtor) -> None:
        d = debtor.delivery_address
        self.draft["delivery_text"] = f"{d.name}\n{d.street}\n{d.zip_code} {d.city}"

    def fill_miscellaneous(self, debtor: Debtor) -> None:
        self.draft["alias"] = debtor.alias

    def payment_methods_offered(self) -> list[str]:
        return [p["name"] for p in self.db.payment_methods]

    def select_payment_method(self, name: str) -> None:
        self.draft["payment"] = name

    def activate(self) -> None:
        self.db.calls.append("debtor.activate")

    def save(self) -> None:
        self.db.calls.append("debtor.save")
        self.db.debtors.append(dict(self.draft))


class FakeList:
    def __init__(self, db: FakeDb, rows: list[dict[str, str]], name: str) -> None:
        self.db, self.rows, self.name = db, rows, name

    def open(self) -> None:
        self.db.calls.append(f"{self.name}.open")

    def search(self, text: str) -> list[dict[str, str]]:
        return [dict(r) for r in self.rows if _contains(r["name"], text)]

    def create_new(self) -> None:
        self.db.calls.append(f"{self.name}.new")


class FakePaymentEditor:
    def __init__(self, db: FakeDb) -> None:
        self.db, self.draft = db, {}

    def fill(self, name: str, payment_code: str) -> None:
        self.draft = {"name": name, "code": payment_code}

    def save(self) -> None:
        self.db.calls.append("payment_method.save")
        self.db.payment_methods.append(dict(self.draft))


class FakeVatEditor:
    def __init__(self, db: FakeDb) -> None:
        self.db, self.draft = db, {}

    def fill(self, name: str, percent: Decimal) -> None:
        self.draft = {"name": name, "value": f"{percent}%", "code": "S (Standard rate)"}

    def save(self) -> None:
        self.db.calls.append("vat.save")
        self.db.vats.append(dict(self.draft))


class FakeProductEditor:
    def __init__(self, db: FakeDb) -> None:
        self.db, self.draft = db, {}

    def open_new_product(self) -> None:
        self.db.calls.append("product.new")

    def vat_options(self) -> list[str]:
        return [v["name"] for v in self.db.vats]

    def fill(self, item: LineItem, gross_price: Decimal, vat_name: str) -> None:
        self.draft = {
            "sku": item.sku,
            "name": item.description,
            "gross": str(gross_price),
            "vat": vat_name.removeprefix("VAT "),
        }

    def save(self) -> None:
        self.db.calls.append("product.save")
        self.db.products.append(dict(self.draft))


class FakeDocuments:
    def __init__(self, db: FakeDb) -> None:
        self.db = db

    def open(self) -> None:
        self.db.calls.append("documents.open")

    def rows_for_reference(self, customer_reference: str) -> list[dict[str, str]]:
        return [dict(d) for d in self.db.documents if d["reference"] == customer_reference]


class FakeInvoiceEditor:
    def __init__(self, db: FakeDb, order: FakeOrderEditor) -> None:
        self.db, self.order = db, order
        self.payment: dict[str, str] = {}

    def wait_until_open(self) -> None:
        self.payment = {"paid": "false", "date": "", "value": ""}
        self.number = f"IN{sum(d['type'] == 'Invoice' for d in self.db.documents) + 1:06d}"

    def read_copied_values(self) -> dict[str, str]:
        totals = self.order.read_totals()
        return {
            "number": self.number,
            "reference": self.order.fields["reference"],
            "vat_mode": "With VAT",
            "order_date": self.order.fields["date"],
            "net": totals["net"],
            "total": totals["total"],
        }

    def read_address_texts(self) -> dict[str, str]:
        return self.order.read_address_texts()

    def read_item_lines(self) -> list[dict[str, str]]:
        return self.order.read_item_lines()

    def payment_methods_offered(self) -> list[str]:
        return [p["name"] for p in self.db.payment_methods]

    def select_payment_method(self, name: str) -> None:
        self.payment["method"] = name

    def mark_paid(self, payment_date: date, value: Decimal) -> None:
        self.payment.update(paid="true", date=payment_date.isoformat(), value=f"${value}")

    def read_payment_state(self) -> dict[str, str]:
        return {k: v for k, v in self.payment.items() if v} | {"paid": self.payment["paid"]}

    def save(self) -> None:
        self.db.calls.append("invoice.save")
        state = "paid" if self.payment["paid"] == "true" else "open"
        self.db.documents.append(
            {
                "type": "Invoice",
                "number": self.number,
                "date": "",
                "reference": self.order.fields["reference"],
                "state": state,
                "total": self.order.read_totals()["total"],
            }
        )


class FakeFakturama:
    def __init__(self, db: FakeDb | None = None) -> None:
        self.db = db or FakeDb()
        self.order = FakeOrderEditor(self.db)
        self.debtor = FakeDebtorEditor(self.db)
        self.payment_methods = FakeList(self.db, self.db.payment_methods, "payment_methods")
        self.payment_method_editor = FakePaymentEditor(self.db)
        self.vats = FakeList(self.db, self.db.vats, "vats")
        self.vat_editor = FakeVatEditor(self.db)
        self.product_editor = FakeProductEditor(self.db)
        self.documents = FakeDocuments(self.db)
        self.invoice = FakeInvoiceEditor(self.db, self.order)
