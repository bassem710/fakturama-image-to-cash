"""The real Fakturama behind the workflow protocols: one screen object per Fakturama screen, sharing one
ScreenContext (session, selectors, settings, workbench, list reader)."""

from __future__ import annotations

from imagetocash.automation.ocr_table import OcrTableReader
from imagetocash.automation.screen_ocr import WindowsScreenOcr
from imagetocash.config import Settings
from imagetocash.fakturama.screen_context import ScreenContext, SelectorMap, connect_session
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
        self.payment_methods = MasterDataListScreen(ctx, "payment_methods", "payment")
        self.payment_method_editor = PaymentMethodEditorScreen(ctx)
        self.vats = VatListScreen(ctx)
        self.vat_editor = VatEditorScreen(ctx)
        self.product_editor = ProductEditorScreen(ctx)
        self.documents = DocumentsListScreen(ctx)
        self.invoice = InvoiceEditorScreen(ctx, self.order)

    @classmethod
    def connect(cls, settings: Settings) -> FakturamaApp:
        selectors = SelectorMap.load(settings.selectors_path)
        session = connect_session(settings, selectors)
        session.bring_to_front()
        ocr = OcrTableReader(WindowsScreenOcr(settings.ocr_language))
        return cls(ScreenContext(session=session, selectors=selectors, ocr=ocr, settings=settings))
