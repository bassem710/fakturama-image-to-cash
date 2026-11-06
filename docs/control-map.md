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

## Lists and dialogs
| Spec | Screen | Status |
|---|---|---|
| 2.2–2.3, 2.12 | Select the address dialog | **?** opened via the icon; contents still to map (NatTable expected → OCR) |
| 3.3, 3.12 | Select a product dialog | **?** |
| 2.5–2.11 | Debtor editor (tabs Addresses / Miscellaneous / Payment) | **?** |
| 2.10.1–2.10.6 | terms of payment list + editor | **?** list = NatTable (OCR), search box = `Edit` after `Text` `Search:` |
| 3.4–3.6 | VATs list + editor | **?** same list layout as Documents |
| 3.7–3.11 | Product editor | **?** |
| 4.5, 5.5 | Data > Documents | List = NatTable pane (OCR); search `Edit` after `Text` `Search:` (verified) |
| 5.1–5.3 | Invoice editor | **?** expected to mirror the Order editor plus paid / payment date / Value |
