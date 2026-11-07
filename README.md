# Fakturama Image-to-Cash

Give it one order image. It books a verified **Order** and a linked **Invoice** in the Fakturama desktop
app, following the take-home spec step by step (1.1 → 5.7).

- **Gemini vision** reads the image.
- **Microsoft UI Automation** drives Fakturama. There are no hardcoded coordinates.
- **Windows OCR** is used only as a fallback, inside a control's UIA rectangle.

## Setup

1. Install Windows 10/11, Python 3.12 and Fakturama **2.2.0** (`C:\Program Files\Fakturama2`).
2. Start Fakturama once and finish its first-run setup: workspace `C:\fakturama`, English UI.
3. Install the project:
   ```bash
   git clone https://github.com/bassem710/fakturama-image-to-cash.git
   cd fakturama-image-to-cash
   python -m venv .venv
   .venv\Scripts\python -m pip install -e ".[dev]"
   .venv\Scripts\activate
   ```
4. Copy `.env.example` to `.env` and set `GEMINI_API_KEY` (from Google AI Studio). No key? Use
   `--from-json` to replay a saved extraction.
5. Turn off Windows clipboard history and "Sync across your devices" (Settings > System > Clipboard).
   The tool reads lists by copying them to the clipboard.

Settings (model, timeouts, date and money formats) are in `config/settings.yaml`.

## Run

```bash
imagetocash run samples/order-page3.png
```

Other commands:

```bash
imagetocash extract samples/order-page3.png                                                  # read the image only (spec 1.1-1.2)
imagetocash run samples/order-page3.png --from-json tests/fixtures/northstar_extracted.json  # replay, no Gemini call
imagetocash inspect --out runs/ui-tree.txt                                                   # dump Fakturama's UIA tree
imagetocash reset-workspace --yes                                                            # restore the clean test database (moves the old one, never deletes)
```

**`imagetocash` is not recognized?** PowerShell prints `The term 'imagetocash' is not recognized as
the name of a cmdlet...` when the virtual environment is not active in that terminal (each new
terminal starts without it). Activate it from the project folder, then run again:

```powershell
.venv\Scripts\Activate.ps1
```

If PowerShell refuses with "running scripts is disabled on this system", allow scripts for this
terminal only and activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Or skip activation and call the venv's copy directly: `.venv\Scripts\imagetocash run samples/order-page3.png`.
If that file does not exist, the install in step 3 did not finish; run it again.

**Exit codes:** `0` done (or already processed) · `2` stopped for manual review · `1` error.

**Results:** every run, pass or fail, writes `runs/<timestamp>/`:
- `report.md`: one row per spec step and the outcome;
- `steps.jsonl` and `run.log`: the same records as JSON;
- screenshots after each stage and at the step that stopped;
- `extracted.json`: what was read from the image (replay it with `--from-json`).

Logs and the report mask customer values. Screenshots and `extracted.json` do not, so don't share
`runs/` as a whole. An annotated example run is in [docs/evidence/](docs/evidence/README.md), with a
[2-minute screen recording](docs/evidence/full-run.mp4) of a full run.

## What it does

| Situation | Result |
|---|---|
| New order, clean workspace | Creates the Debtor, payment method, VAT rate and Products, then the Order and the paid Invoice. About 2 minutes on an idle machine (low free RAM can double it), verified live. |
| Same image again | Changes nothing. Finds the booked Order and Invoice, checks them, exits "already processed". |
| Known customer, new order | Reuses the existing records (no duplicates) and books a new Order and Invoice. |
| Anything unclear (two matches, wrong totals, a record that doesn't show up) | Stops for manual review: logs why, takes a screenshot, exits `2`. |

## How it works

```
cli ─▶ workflow (stages 1-5 = spec sections) ─▶ domain (pricing, validation, matching)
          ├─▶ fakturama (screens, selectors.yaml) ─▶ automation (UIA, OCR, evidence)
          └─▶ extraction (Gemini, parsing) ─▶ domain
```

- **One module per spec section** (`workflow/stage1_open_order.py` … `stage5_invoice.py`).
- **Check the data first.** Every line, the totals and the payment date are checked with `Decimal`
  math before Fakturama is touched.
- **Check every step.** Each field is typed, read back and retried once; then the run stops for review.
- **One matching rule** for Debtor, payment method, Product and VAT: one exact match → use it; none →
  create it; anything else → stop.
- **No duplicate bookings.** Before creating anything, step 1.2.1 looks for the image's External
  Reference in Data > Documents.
- **All UI names** are in `config/selectors.yaml`. Fakturama quirks are listed in
  [docs/control-map.md](docs/control-map.md) under Gotchas.

Design and trade-offs: [docs/design-doc.md](docs/design-doc.md).

### Deliberate spec deviations

1. **Step 1.2.1, the duplicate guard,** is an added read-only step.
2. **The payment method is created before New Contact.** Fakturama doesn't show a method created
   while a Debtor editor is open (gotcha 15).
3. **Rows are chosen with a double-click.** In the two selection dialogs, and to open an existing VAT
   rate, Fakturama accepts only a double-click. The click point is measured inside the list element
   at run time. It's the one pointer action, in `fakturama/row_choice.py` (gotcha 7).

## Tests

```bash
.venv\Scripts\python -m pytest          # 103 tests, no Fakturama or network needed
.venv\Scripts\ruff check src tests
.venv\Scripts\python -m mypy src
```

## Deliverables

| Asked for in the brief | Where |
|---|---|
| Design doc (Part 1) | [docs/design-doc.md](docs/design-doc.md) |
| Source code in a Git repo | `src/imagetocash/`, tests in `tests/` |
| Setup and run instructions | [Setup](#setup), [Run](#run) |
| Annotated screenshots or a short recording | Both: [screen recording of a full run](docs/evidence/full-run.mp4) (2 min, captioned by spec step) and [annotated screenshots](docs/evidence/README.md) |
| What was skipped | [Not done / next steps](#not-done--next-steps) |
| Written question | [Written question](#written-question) |

## Not done / next steps

1. **Half-booked orders are not resumed.** An Order without its Invoice (for example, a run stopped at
   4.6) stops for manual review instead of finishing the Invoice.
2. **Order-level discount or shipping** on the image (4.2) stops for review instead of being set.
3. **A reused VAT rate whose code isn't S** stops for review. Only unit tests cover this; the normal
   path (code S) is verified live.
4. **Tested live on one setup only:** Fakturama 2.2.0, en_US, a maximized window on 1920×1080 and
   2560×1440 screens. Other window sizes and scaling are not verified live.

## Written question

**If you had 3 more hours, what would you do?**

1. **Resume instead of stop** (about 1.5 h). Finish a half-booked order: open the existing Order from
   Documents and create its missing Invoice, or open an unpaid Invoice and mark it paid, with the same
   checks as a fresh run.
2. **Prove robustness** (about 45 min). Run at another window size and scaling, plus two more order
   images (one unpaid, one with the same delivery address), and keep their evidence as regression
   fixtures.
3. **Golden tests for the list readers** (about 45 min). Save real list copies and screenshots as test
   fixtures, so a change in Fakturama's format fails in CI instead of in a live run.
