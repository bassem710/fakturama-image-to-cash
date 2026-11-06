# Fakturama 2.2.0 control map (UI Automation discovery)

How each control in the flow is reached, and what Fakturama does that is not obvious. Built with
`imagetocash inspect` (pywinauto, `backend="uia"`) on Windows 11, Fakturama 2.2.0 (Eclipse RCP / SWT),
en_US locale. Every name below lives in [`config/selectors.yaml`](../config/selectors.yaml); code only
refers to keys.

Legend: **UIA** = found by UIA properties · **Label** = unnamed control found after its label ·
**Order** = unnamed control told apart by its order inside a labeled container · **Copy** = custom-drawn
NatTable list read by its own Ctrl+A / Ctrl+C binding (OCR inside the UIA rectangle only as a fallback).

## Session facts
| Fact | Consequence |
|---|---|
| Main window: class `SWT_Window0`, title `Fakturama - <workspace>` | Found once by class through `Application.windows()`, then addressed by **handle**: criteria lookups miss a minimized SWT window. |
| Only the ACTIVE editor's controls exist in the UIA tree | Always activate this run's editor tab before locating its fields (`fakturama/workbench.py`). |
| A UIA `FindAll` walks SWT's whole tree (~0.4 s on the main window), `FindFirst` stops at the first hit (~0.01 s) | Named lookups use `find_first`; an editor's tab item and pane are kept once found (`automation/locators.py`, `workbench.py`). |
| Locale en_US: dates `Nov 6, 2026`, money `$0.00` | Formats in `config/settings.yaml`; values parsed in `fakturama/values.py`. |
| A fresh, empty database refuses a New Order ("No default value found for Shippings") | Test resets restore Fakturama's own backup taken right after first setup (`imagetocash reset-workspace --yes`). |

## Main window
| Spec | Control | How | Selector |
|---|---|---|---|
| 1.3 | Toolbar **Order** | UIA | `Button` `Create: New Order` (Invoke) |
| 2.11, 3.6, 3.11, 4.4, 5.4 | Toolbar **Save** | UIA | `Button` `Save the current contents` (Invoke) |
| 2.5 | New panel **New Contact** | UIA | `Text` `New Contact` (no pattern: element click); toolbar `SplitButton` `Create a new contact` as fallback |
| 3.7 | New panel **New product** | UIA | `Text` `New product`; toolbar `Create a new product` as fallback |
| 1.2.1, 2.10.1, 3.4, 4.5 | **Data** menu | UIA | `MenuItem` `Data` (ExpandCollapse) → `MenuItem` view title (Invoke) |
| – | Editor / view tabs | UIA | `TabItem` named after the title (`*` prefix = unsaved) |

## Order editor (tab `New Order`, renamed to the number on Save)
| Spec | Field | How | Selector / notes |
|---|---|---|---|
| 1.4 | **No.** | Label | `Edit` after `No.` |
| 1.5 | **Date** | Label | CDateTime `Edit` after `Date`: entered by keyboard (see Gotchas) |
| 1.7 | Price mode | Label | unnamed `ComboBox` after `Date` → `Net` |
| 1.7 | VAT mode | UIA | `ComboBox` `VAT`, stays `With VAT` |
| 1.6 | **Cust.Ref.** | UIA | `Edit` `Cust.Ref.` |
| 2.1 | Select existing contact | Order | 1st (upper) `Image` beside `Addresses`; the 2nd (green +) is never used |
| 2.4, 2.13 | Invoice / Delivery address | UIA | `TabItem`s `Invoice address` / `Delivery address`; content = multi-line `Edit`: name, contact, street, `DE-10117 Berlin`, country name on its own line (checked: street, ZIP, city, country as a whole line) |
| 3.2 | Select product | Order | 1st (upper) `Image` beside `Items` |
| 3.13–3.16 | Items grid | Copy | NatTable right of `Items`; edited by keyboard (see Gotchas) |
| 4.2 | Discount / Shipping | UIA | `Edit` `Discount`; `ComboBox` `Shipping` (`Free of shipping costs`) |
| 4.3 | Totals | UIA | `Edit`s `Total Net` (or `Total Gross`), `VAT`, `Total` |
| 4.6 | Follow-up **Invoice** | UIA | `Button` `Invoice` in `Create a follow-up document` (Invoke) |

## Lists, dialogs, other editors
| Spec | Screen | How |
|---|---|---|
| 2.2–2.3, 2.12 | **Select the address** (top-level `#32770`) | Search = `Edit` after `Search:`; list copies **No., First Name, Name, Company, ZIP, City** (+3 hidden columns, ignored). |
| 3.3, 3.12 | **Select a product** | Same layout; copies **Item No., Name, Description, Stock, Price, VAT**. |
| 2.5–2.9 | **New Debtor** | `Company`; `First Name Last Name` label → 2 `Edit`s. Addresses → `Main address`: `additional name`, `Street`, `ZIP - City` (2 `Edit`s), `Country`, `E-Mail`, `Telephone`; `+` adds `additional address #1`. Roles: button after `address type` opens a popup window with CheckBoxes `Invoice address` / `Delivery address`. |
| 2.9–2.10 | Debtor **Miscellaneous** | `Alias name`, `Discount`, `Net or Gross`, `Payment` (lists payment-method descriptions). |
| 2.10.1–2.10.6 | **terms of payment** + **New Term of Payment** | List copies Standard, Name, Description, Discount, Disc. Days, Net Days. Payment code combo is named `!editorPaymentPaymentcode!` (untranslated key); options are space-padded (`'Credit transfer '`). |
| 3.4–3.6 | **VATs** + **New TAX Rate** | List copies Standard, Name, Description, Value (a fraction); no VAT code column. Editor: `Name`, `Description`, `VAT code (E-Invoice)`, `Value`. |
| 3.7–3.11 | **New product** | `Item Number`, `Name`, `Description`, `Price (gross)` / `cost price (net)` (after labels), `VAT` combo, `Stock`. |
| 1.2.1, 4.5, 5.5 | **Documents** | Copies type icon, **Document, Date, Name, Cust.Ref., State, Total, Printed**. Type from the number prefix (`PO`, `IN`). |
| 5.1–5.3 | Invoice editor | Order layout plus `Service date`, `Order Date`; `paid` CheckBox → method combo; once ticked: `at` (CDateTime) and `Value`. |

## Gotchas found live
| # | Behavior | Handling (where) |
|---|---|---|
| 1 | `SelectionItem.Select()` on SWT tabs raises or returns without switching | `select_tab_item`: verify `IsSelected`, else click the tab element (`automation/input.py`) |
| 2 | `ValuePattern.SetValue` changes an editor field's text but **not** Fakturama's data binding (a Debtor was saved without its company) | Editor fields are **typed** and read back (`set_and_verify`). SetValue is used only for the selection-dialog search box, which has no binding |
| 3 | `SelectionItem.Select()` on a dropdown option changes the text but fires no SWT event: the old value is saved (a Product saved as VAT *Tax-free*) | Options are searched: type the option's letters on the focused combo until it shows the option, then one arrow away and back (gotcha 19). Fallbacks: Up/Down from the current option, then a click on the option element (`select_combo_option`) |
| 4 | Multi-line Edits insert a tab character on Tab | No commit key when typing; read-back compares exactly |
| 5 | Nebula CDateTime reverts a `SetValue`; Tab into it selects the first part; typed digits move on by themselves | Focus the previous field, Tab, confirm focus through UIA, type `MMDDYYYY`, leave, verify (`automation/date_input.py`) |
| 6 | **Select a product** applies its row by itself as soon as its filter leaves exactly one (typing `CHR-ERG-01` applied an unrelated product at `CH`) | Search set in one event; a dialog that closes alone is `auto_applied` and the new Items line must carry the exact SKU (`selection_dialog.py`, stage 3) |
| 7 | The selection dialogs apply a row only on a mouse double-click (keyboard + OK applies nothing) | The one pointer exception: double-click inside the list element at a point measured at run time (`fakturama/row_choice.py`) |
| 8 | NatTable copy: no header, raw values, `null` for empty; VAT as a fraction; the Items grid copies a whole VAT record (`taxValue: [0.19]`) and a line discount as a **negative** fraction (`-0.1` = 10 %); the row-number column is not copied | `fakturama/values.py`, `items_order` in selectors.yaml |
| 9 | Ctrl+C on an **empty** NatTable shows "Internal Error … copiedCells is null" | A quick OCR look first where a list may be empty; that exact error is acknowledged as "empty", any other Internal Error stops the run (`fakturama/tables.py`) |
| 10 | Keys sent right after a focus change can be dropped (a lost Ctrl+A copies one row; a lost Right puts U.Price into Qty.) | `focus()` waits for UIA focus and settles; Items edits re-read the whole line and repair once, else stop |
| 11 | Fakturama can leave a grid cell editor open; keys then go into it and the table vanishes from UIA | Escape before and after each cell edit |
| 12 | **Order Save fails** (NullPointerException in `DocumentEditor.doSave`) while the *Delivery address* tab is selected | Reading the addresses ends with *Invoice address* selected again (`order_editor.read_address_texts`) |
| 13 | Documents **State** copies the key of its icon (`COMMAND_ORDER_PENDING`, `COMMAND_CHECKED`), **Date** copies Java's date text | Mapped to `open` / `paid` (selectors.yaml) and ISO dates (`values.iso_date`) |
| 14 | A checkbox's Toggle state reads stale for a moment after Toggle (Invoice `paid`); the Debtor role popup's state never reads right | `set_checkbox` polls; roles are verified through the `address type` field instead |
| 15 | A payment method created while a Debtor editor is open never appears in that editor's Payment combo | The method is created before New Contact (2.10.1–2.10.6, then 2.5) |
| 16 | The New panel entry sometimes only re-focuses an open "new" editor | After 4 s without a new tab, the toolbar button (logged as a warning) |
| 17 | OCR fallback: `%` read as `0/0`; O/0 and I/1 confused in codes | `fix_ocr_percent`; confusable-tolerant comparison on both sides |
| 18 | "Save Parts" (closing dirty editors): checkbox state not readable | Editors are never closed by the run; each is saved once with the toolbar |
| 19 | A dropdown selection made by **letters alone** (list open + Enter, or closed) shows the option, but the binding keeps an earlier prefix hit: Country showed *Germany*, the database saved `GE` (Georgia) | After the letter search, `{DOWN}{UP}` (`{UP}{DOWN}` on the last option) so the last change is an arrow key; verified in the database (`DE`, payment code `30`, VAT `S`). Addresses now also check the country line |
| 20 | A field that validates per key (E-Mail) can show the last keystroke a moment late | `set_and_verify` polls the read-back for up to 1 s before retyping |
