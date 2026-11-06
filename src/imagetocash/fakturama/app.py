"""The real Fakturama behind the workflow protocols (composition of the screen objects)."""

from __future__ import annotations

from imagetocash.automation.ocr_table import OcrTableReader
from imagetocash.automation.screen_ocr import WindowsScreenOcr
from imagetocash.automation.session import DesktopSession
from imagetocash.cli.config import Settings
from imagetocash.fakturama.screen_context import ScreenContext, SelectorMap
from imagetocash.fakturama.screens.debtor_editor import DebtorEditorScreen
from imagetocash.fakturama.screens.documents_list import DocumentsListScreen
from imagetocash.fakturama.screens.invoice_editor import InvoiceEditorScreen
from imagetocash.fakturama.screens.master_data import (
    MasterDataListScreen,
    PaymentMethodEditorScreen,
    VatEditorScreen,
    VatListScreen,
)
from imagetocash.fakturama.screens.order_editor import OrderEditorScreen
from imagetocash.fakturama.screens.product_editor import ProductEditorScreen


class FakturamaApp:
    def __init__(self, ctx: ScreenContext) -> None:
        self.order = OrderEditorScreen(ctx)
        self.debtor = DebtorEditorScreen(ctx)
        self.payment_methods = MasterDataListScreen(ctx, "payment_methods", "payment_columns")
        self.payment_method_editor = PaymentMethodEditorScreen(ctx)
        self.vats = VatListScreen(ctx)
        self.vat_editor = VatEditorScreen(ctx)
        self.product_editor = ProductEditorScreen(ctx)
        self.documents = DocumentsListScreen(
            MasterDataListScreen(ctx, "documents", "documents_columns"),
            ctx.ui_date_parse_format,
            ctx.selectors.value("lists", "document_type_by_prefix"),
            ctx.selectors.value("lists", "document_state_by_key"),
        )
        self.invoice = InvoiceEditorScreen(ctx, self.order)

    @classmethod
    def connect(cls, settings: Settings) -> FakturamaApp:
        session = DesktopSession.attach_or_launch(settings.fakturama_exe, timeout=settings.timeouts.app_start)
        session.bring_to_front()
        ctx = ScreenContext(
            session=session,
            selectors=SelectorMap.load(settings.selectors_path),
            tables=OcrTableReader(WindowsScreenOcr(settings.ocr_language)),
            settings=settings,
        )
        return cls(ctx)
