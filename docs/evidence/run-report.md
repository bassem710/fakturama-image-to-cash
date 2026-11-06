# Run report: DONE: Order and linked Invoice saved and verified

Values are masked (first/last character and length); see automation/run_log.py.

| # | Spec | Action | Expected | Observed | Result | s | Screenshot |
|---|---|---|---|---|---|---|---|
| 1 | 1.1 | Extract and normalize the order image | o***g (15 chars) | # item(s), total # EUR | ✔ | 0.0 |  |
| 2 | 1.2 | All required fields extracted |  | {'r***e (# chars)': 'W***# (# chars)', 'd***r (# chars)': 'N***H (# chars)', 'p***t (# chars)': 'B***r (# chars)', 'p***d (# chars)': 'P***D (# chars)'} | ✔ | 0.0 |  |
| 3 | 1.2.1 | Already booked? Data > Documents by Cust.Ref. | W***7 (17 chars) | not booked yet | ✔ | 1.83 |  |
| 4 | 1.3 | Click toolbar Order, wait for the New Order editor |  |  | ✔ | 2.31 |  |
| 5 | 1.4 | Leave the proposed No. unchanged |  | PO0# | ✔ | 0.0 |  |
| 6 | 1.5 | Set Date to the Order Date | 2***4 (10 chars) |  | ✔ | 0.97 |  |
| 7 | 1.6 | Enter External Reference in Cust.Ref. | W***7 (17 chars) |  | ✔ | 0.2 |  |
| 8 | 1.7 | Price mode Net, VAT stays With VAT | N***T (14 chars) | With VAT | ✔ | 0.47 |  |
| 9 | 1.8 | Keep this New Order tab open for the rest of the flow |  |  | ✔ | 0.0 |  |
| 10 | 2.1 | Open Select the address (upper icon beside Addresses) |  |  | ✔ | 1.86 |  |
| 11 | 2.2 | Search by company / customer name | N***H (21 chars) | # row(s) | ✔ | 0.89 |  |
| 12 | 2.3 | Exact match on Company, First Name, Name, ZIP, City |  | no exact row -> Cancel, create the Debtor | ✔ | 2.75 |  |
| 13 | 2.10.1 | Data > terms of payment: search the exact method |  | # row(s) | ✔ | 2.55 |  |
| 14 | 2.10.2 | One exact row -> reuse; none -> green + |  | none -> new payment method | ✔ | 1.53 |  |
| 15 | 2.10.5 | Cash discount, Discount Days, Net Days #; texts blank; not standard |  |  | ✔ | 1.23 |  |
| 16 | 2.10.4 | Payment code | C***r (15 chars) |  | ✔ | 1.23 |  |
| 17 | 2.10.3 | Name = Description = method; Account blank |  |  | ✔ | 1.23 |  |
| 18 | 2.10.6 | Save the payment method once |  |  | ✔ | 0.66 |  |
| 19 | 2.5 | Keep Order open; New Contact in the New panel |  |  | ✔ | 1.62 |  |
| 20 | 2.6 | Company, First Name, Last Name; keep Customer ID and Salutation |  |  | ✔ | 0.94 |  |
| 21 | 2.7 | Main address: Street, ZIP, City, Country, E-Mail, Telephone |  |  | ✔ | 2.5 |  |
| 22 | 2.8 | Assign address roles | I***) (37 chars) |  | ✔ | 3.64 |  |
| 23 | 2.9 | Miscellaneous: Alias name, Discount #%, Net |  |  | ✔ | 1.56 |  |
| 24 | 2.10 | Payment: select the exact Payment Method | B***r (13 chars) | selected | ✔ | 0.91 |  |
| 25 | 2.11 | Save the Debtor once |  |  | ✔ | 0.53 |  |
| 26 | 2.12 | Back on the Order: search again, select the new Debtor, OK |  | new Debtor selected | ✔ | 6.23 |  |
| 27 | 2.13 | Invoice / Delivery address populate correctly |  |  | ✔ | 1.44 |  |
| 28 | 3.1 | Process # item(s) in source order |  |  | ✔ | 0.0 |  |
| 29 | 3.2 | [CHR-ERG-#] Open Select a product (upper icon beside Items) |  |  | ✔ | 1.64 |  |
| 30 | 3.3 | [CHR-ERG-#] Search the exact SKU |  | no exact SKU -> Cancel, create the Product | ✔ | 3.52 |  |
| 31 | 3.4 | [CHR-ERG-#] Data > VATs: search VAT #% |  | # row(s) | ✔ | 2.39 |  |
| 32 | 3.5 | [CHR-ERG-#] Reuse only Name/Value/code S exact |  | missing -> create (#) | ✔ | 0.0 |  |
| 33 | 3.6 | [CHR-ERG-#] Create VAT #% (code S, value #), save once |  |  | ✔ | 2.61 |  |
| 34 | 3.7 | [CHR-ERG-#] New product (VAT now in the dropdown) |  | Free of Tax, VAT #% | ✔ | 1.78 |  |
| 35 | 3.10 | [CHR-ERG-#] cost price # VAT VAT #%, Stock # |  |  | ✔ | 1.67 |  |
| 36 | 3.9 | [CHR-ERG-#] Price (gross) | 2***0 (6 chars) |  | ✔ | 1.67 |  |
| 37 | 3.8 | [CHR-ERG-#] Item Number, Name, Description |  |  | ✔ | 1.67 |  |
| 38 | 3.11 | [CHR-ERG-#] Save the Product once |  |  | ✔ | 0.52 |  |
| 39 | 3.12 | [CHR-ERG-#] Back on the Order: select the new Product |  | new Product selected | ✔ | 6.3 |  |
| 40 | 3.15 | [CHR-ERG-#] Discount | *** (3 chars) |  | ✔ | 3.7 |  |
| 41 | 3.14 | [CHR-ERG-#] U.Price / VAT | 2***% (12 chars) |  | ✔ | 3.7 |  |
| 42 | 3.13 | [CHR-ERG-#] Qty. | *** (1 chars) |  | ✔ | 3.7 |  |
| 43 | 3.16 | [CHR-ERG-#] Line Price = qty x net x (# - disc) |  | USD # | ✔ | 0.0 |  |
| 44 | 3.2 | [MAT-DESK-#] Open Select a product (upper icon beside Items) |  |  | ✔ | 1.81 |  |
| 45 | 3.3 | [MAT-DESK-#] Search the exact SKU |  | no exact SKU -> Cancel, create the Product | ✔ | 3.53 |  |
| 46 | 3.4 | [MAT-DESK-#] Data > VATs: search VAT #% |  | # row(s) | ✔ | 2.8 |  |
| 47 | 3.5 | [MAT-DESK-#] Reuse only Name/Value/code S exact |  | reuse existing VAT | ✔ | 0.0 |  |
| 48 | 3.7 | [MAT-DESK-#] New product (VAT now in the dropdown) |  | Free of Tax, VAT #% | ✔ | 1.86 |  |
| 49 | 3.10 | [MAT-DESK-#] cost price # VAT VAT #%, Stock # |  |  | ✔ | 1.11 |  |
| 50 | 3.9 | [MAT-DESK-#] Price (gross) | 4***0 (5 chars) |  | ✔ | 1.11 |  |
| 51 | 3.8 | [MAT-DESK-#] Item Number, Name, Description |  |  | ✔ | 1.11 |  |
| 52 | 3.11 | [MAT-DESK-#] Save the Product once |  |  | ✔ | 0.53 |  |
| 53 | 3.12 | [MAT-DESK-#] Back on the Order: select the new Product |  | new Product selected | ✔ | 2.77 |  |
| 54 | 3.15 | [MAT-DESK-#] Discount | *** (2 chars) |  | ✔ | 1.23 |  |
| 55 | 3.14 | [MAT-DESK-#] U.Price / VAT | 4***% (11 chars) |  | ✔ | 1.23 |  |
| 56 | 3.13 | [MAT-DESK-#] Qty. | *** (1 chars) |  | ✔ | 1.23 |  |
| 57 | 3.16 | [MAT-DESK-#] Line Price = qty x net x (# - disc) |  | USD # | ✔ | 0.0 |  |
| 58 | 3.17 | Every source item has its line on the Order |  | # line(s) | ✔ | 0.64 |  |
| 59 | 4.1 | Debtor addresses and every line match the image |  |  | ✔ | 2.27 |  |
| 60 | 4.2 | Discount #%, Shipping free / # unless the image says otherwise |  |  | ✔ | 0.0 |  |
| 61 | 4.3 | Total Net, VAT, Total match the source | S***) (83 chars) | {'*** (# chars)': '$***# (# chars)', '*** (# chars)': '$***# (# chars)', 't***l (# chars)': '$***# (# chars)'} | ✔ | 0.0 |  |
| 62 | 4.4 | Click the toolbar Save once |  |  | ✔ | 0.58 |  |
| 63 | 4.5 | Data > Documents: one open Order row with the generated number |  | {'t***e (# chars)': 'o***r (# chars)', 'n***r (# chars)': 'P***# (# chars)', 'd***e (# chars)': '#***# (# chars)', 'c***r (# chars)': 'N***n (# chars)', 'r***e (# chars)': 'W***# (# chars)', 's***e (# chars)': 'o***n (# chars)', 't***l (# chars)': '#***# (# chars)', 'p***d (# chars)': '<empty>'} | ✔ | 2.81 |  |
| 64 | 4.6 | Create a follow-up document > Invoice (not the toolbar) |  |  | ✔ | 0.95 |  |
| 65 | 4.7 | Wait for the linked New Invoice editor |  |  | ✔ | 1.05 |  |
| 66 | 5.1 | Leave No./dates; values were copied from the Order |  | {'n***r (# chars)': 'I***# (# chars)', 'r***e (# chars)': 'W***# (# chars)', 'o***e (# chars)': '#***# (# chars)', 'v***e (# chars)': 'W***T (# chars)', '*** (# chars)': '$***# (# chars)', 't***l (# chars)': '$***# (# chars)'} | ✔ | 2.42 |  |
| 67 | 5.2 | Invoice payment method = extracted method | B***r (13 chars) |  | ✔ | 0.22 |  |
| 68 | 5.3 | Paid Status PAID | p***0 (32 chars) | {'p***d (# chars)': 't***e (# chars)', 'd***e (# chars)': '#***# (# chars)', 'v***e (# chars)': '#***# (# chars)'} | ✔ | 1.45 |  |
| 69 | 5.4 | Click the toolbar Save once |  |  | ✔ | 0.64 |  |
| 70 | 5.5 | Data > Documents: Invoice state/Total; Order still open |  | paid | ✔ | 2.98 |  |
| 71 | 5.7 | End: no Delivery, Correction or Dunning document |  |  | ✔ | 0.0 |  |
