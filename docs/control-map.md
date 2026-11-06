# Fakturama 2.2.0 control map (UI Automation discovery)

How each control in the flow is reached. Built with `imagetocash inspect` (pywinauto, `backend="uia"`)
on Windows 11, 1920×1080, Fakturama 2.2.0 (Eclipse RCP / SWT 3.124), en_US locale.

Legend: **UIA** = found by UIA properties · **Label** = unnamed control found next to its label ·
**Order** = unnamed control told apart by its order inside a labeled UIA container · **OCR** = custom-drawn,
read with Windows OCR inside the UIA rectangle · **?** = not yet discovered (needs a live pass).

## Session facts
| Fact | Consequence |
|---|---|
| Main window: class `SWT_Window0`, title `Fakturama - <workspace>` | Found via `Application.windows()` by class, then addressed by **handle**. Criteria lookups (`title_re`/`class_name`) fail when the window is minimized. |
| Window may be minimized / behind other apps | Session restores, maximizes and focuses it before every stage. |
| Locale en_US: dates `Nov 6, 2026`, money `$0.00` | Date typed as `%b %-d, %Y`; amounts parsed with `parse_amount` (ignores `$`). Configurable in `config/settings.yaml`. |

## Main window (verified)
| Spec | Control | How | Selector |
|---|---|---|---|
| 1.3 | Toolbar **Order** | UIA | `Button` name `Create: New Order` (Invoke) |
| 2.11, 3.6, 3.11, 4.4, 5.4 | Toolbar **Save** | UIA | `Button` name `Save the current contents` (Invoke) |
| 2.5 | New panel **New Contact** | UIA | `Text` name `New Contact` in `Navigation View` (no Invoke → click its UIA rect) |
| 3.7 | New panel **New product** | UIA | `Text` name `New product` in `Navigation View` |
| 2.10.1 / 3.4 / 4.5 | **Data** menu | UIA | `MenuBar` `Application` → `MenuItem` `Data` (ExpandCollapse) |
| – | Navigation **Documents / VATs / terms of payment** | UIA | `Text` items in `Navigation View` (same targets as the Data menu) |
| – | Editor tabs | UIA | `TabItem` name = editor title (`New Order`, …), SelectionItem pattern |

## Order editor (verified, tab `New Order`)
| Spec | Field | How | Selector / notes |
|---|---|---|---|
| 1.4 | **No.** | Label | `Edit` after `Text` `No.` → value `PO000001` |
| 1.5 | **Date** | Label | `Edit` (inside CDateTime pane) after `Text` `Date` → value `Nov 6, 2026` |
| 1.7 | Price mode | Label/Order | unnamed `ComboBox` right of Date, value `Gross` → set `Net` |
| 1.7 | VAT mode | UIA | `ComboBox` name `VAT` (in header), value `With VAT` |
| 1.6 | **Cust.Ref.** | UIA | `Edit` name `Cust.Ref.` |
| 2.1 | Select existing contact | Order | 1st (upper) `Image` in the container of `Text` `Addresses` |
| – | New contact (+), **never used** | Order | 2nd (lower) `Image` in the same container |
| 2.4, 2.13 | Invoice / Delivery address | UIA | `Tab` named after the address role, inner multi-line `Edit` (Value) |
| 3.2 | Select product | Order | 1st (upper) `Image` in the container of `Text` `Items` |
| 3.13–3.16 | Items grid | OCR | NatTable pane right of `Items` (opaque in UIA) |
| 4.2 | Discount | UIA | `Edit` name `Discount` (`0%`) |
| 4.2 | Shipping | UIA | `ComboBox` name `Shipping` (`Free of shipping costs`) + unnamed `Edit` value (`$0.00`) |
| 4.3 | Total Net / VAT / Total | UIA | `Edit` names `Total Gross`→(`Total Net` in Net mode), `VAT`, `Total` |
| 4.6 | Follow-up **Invoice** | UIA | `Group` `Create a follow-up document` → `Button` `Invoice` (Invoke) |

## Lists and dialogs (verified 2026-11-06)
| Spec | Screen | How |
|---|---|---|
| 2.2–2.3, 2.12 | **Select the address**: top-level `#32770` window | Search = Edit after `Search:`; OK / Cancel = Buttons (Invoke); list = custom-drawn pane (scrollbar children only) → OCR. Columns **No., First Name, Name, Company, ZIP, City**, headers **centred** → columns from grid lines. Narrow columns truncate with `...` → prefix match. |
| 3.3, 3.12 | **Select a product**: same layout | Columns **Item No., Name, Description, Stock, Price, VAT** (left-aligned). |
| 2.5–2.9 | **New Debtor** editor | Company = Edit `Company`; `First Name Last Name` label → 2 Edits (nth 0/1). Tabs Addresses / Miscellaneous / Notice. Addresses → `Main address` tab: `additional name`, `Street`, `ZIP - City` (2 Edits), `Country` combo, `E-Mail`, `Telephone`; `+` adds `additional address #1` (same fields). Roles: Button after `address type` opens a popup (child `#32770` pane of the main window) with CheckBoxes **Invoice address** / **Delivery address** (Toggle). |
| 2.9–2.10 | Debtor **Miscellaneous** tab | `Alias name`, `Discount`, `Net or Gross` (`---`/Net/Gross), **`Payment`** combo (lists payment-method *descriptions*). |
| 2.10.1–2.10.2 | **terms of payment** list | Columns Standard, Name, Description, Discount, Disc. Days, Net Days; green + = Button `Create a new term of payment`. |
| 2.10.3–2.10.6 | **New Term of Payment** editor | `Name`, `Description`, `Account`; payment code combo is named **`!editorPaymentPaymentcode!`** (Fakturama's untranslated key). Options are space-padded (`'Credit transfer '`). Cash discount / Discount Days / Net Days default to 0. |
| 3.4–3.5 | **VATs** list | Columns Standard, Name, Description, Value; **no VAT code column** → the matching row is opened (double-click), `VAT code (E-Invoice)` read, editor closed (Ctrl+W). Green + = `Create a new tax rate`. |
| 3.6 | **New TAX Rate** editor | `Name`, `Description`, `VAT code (E-Invoice)` (default `S (Standard rate)`), `Value` (`0%`), `Set as standard` (never clicked). |
| 3.7–3.11 | **New product** editor | `Item Number`, `Name`, `Description` (multi-line), `Price (gross)` / `cost price (net)` = Edits after labels, `VAT` combo (lists VAT *descriptions*), `Stock`. |
| 4.5, 5.5 | **Documents** list | Icon-only type column, then **Document, Date, Name, Cust.Ref., State, Total, Printed**; type derived from the number prefix (`PO…` = Order). |
| 5.1–5.3 | Invoice editor | Same as the Order editor plus `Service date`, `Order Date`; **`paid` CheckBox** → payment-method combo after it; when ticked: `at` (date) and `Value`. Follow-up group: Delivery, Invoice Correction, Dunning (never used). |

## Gotchas found live
| Behavior | Handling |
|---|---|
| `SelectionItem.Select()` on SWT tabs either raises "Member not found" or returns without switching the editor | `select_tab_item`: verify `IsSelected`, else click the tab's UIA rectangle |
| Hidden editors' content is absent from the UIA tree | Always activate the editor tab before locating its fields |
| Company and Description Edits are multi-line: Tab inserts a tab character | No commit key when typing; read-back compares exactly (ends trimmed only) |
| Nebula CDateTime ignores UIA `SetValue` (reverts on focus loss) and edits one field at a time | `date_input.set_cdatetime`: probe the selected field with Up/Down, move with Right, type zero-padded digits year→month→day, verify after focus leaves |
| Windows OCR reads the list's `%` as `0/0` | `fix_ocr_percent` before parsing / comparing |
| Windows OCR confuses O/0 and I/1 in codes (`CHR-ERG-OI`) | OCR-tolerant comparison on both sides |
| Combo options carry trailing spaces | Select the option whose normalized text matches, by its exact name |
| **"Save Parts" dialog (closing dirty editors): the checkbox state is NOT readable through UIA/MSAA** | Never close dirty editors programmatically; the run saves each editor once via the toolbar, as the spec says |
