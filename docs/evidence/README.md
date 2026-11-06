# Evidence: one full run on a clean workspace

Annotated screenshots from a live run of `imagetocash run samples/order-page3.png` against Fakturama
2.2.0 (en_US), starting from a clean workspace (`imagetocash reset-workspace --yes`). Every master record
was missing, so this run takes every creation branch. Result: **exit 0, 71 spec steps, 110 s**.
Red boxes mark what each spec step set or verified. The order data is the sample from page 3 of the
take-home PDF.

| Screenshot | Spec steps shown |
|---|---|
| [01_order_header_and_debtor.png](01_order_header_and_debtor.png) | 1.3–1.8 New Order header (No. kept, Date, Cust.Ref., Net, With VAT); 2.10.1–2.10.6 payment method created; 2.5–2.13 Debtor created, then selected from the Order |
| [02_items_and_totals.png](02_items_and_totals.png) | 3.4–3.6 VAT 19 % created once; 3.7–3.12 both Products created and selected by exact SKU; 3.13–3.16 lines completed; 4.2–4.3 order-level defaults and totals |
| [03_order_saved_invoice_opened.png](03_order_saved_invoice_opened.png) | 4.4–4.5 Order saved, one open Order row in Documents; 4.6–4.7 linked Invoice opened from "Create a follow-up document"; 5.1 values copied |
| [04_invoice_paid_and_verified.png](04_invoice_paid_and_verified.png) | 5.2–5.3 payment method, paid, payment date, full Total; 5.4 saved once; 5.5 Invoice paid and Order still open |

[run-report.md](run-report.md) is that run's own report: one row per spec step with expected / observed
values (masked), result and duration. Re-running the same image afterwards changes nothing: step 1.2.1
finds the booked Order + Invoice and the run ends "already processed" (exit 0, 3 steps, 3 s).

Values saved in Fakturama's database were also checked directly after the run: country `DE` on both
addresses, payment code `30` (Credit transfer), VAT 19 % with code `S`, both Products linked to it.

The extra editor tabs in the tab bar (an older `New Order`, `INV000001`) are restored by Fakturama's own
workbench layout from earlier sessions; the run tracks its editors by identity and never touches them.
