# Fakturama Image-to-Cash

Turns one order image into a saved, verified **Order** and linked **Invoice** in the Fakturama desktop
app, following the take-home spec step by step (1.1 → 5.7). It uses **Microsoft UI Automation** to drive
the app, **Gemini vision (Google AI Studio)** to read the image, and **Windows OCR** only as a fallback
inside UI Automation rectangles. No hardcoded coordinates: every target comes from UIA at run time.

## Status

| Part | State |
|---|---|
| Full live run 1.1 → 5.7 on a clean workspace | **Passes**: creates the Debtor, payment method, VAT 19 %, both Products, the Order and the paid Invoice, verifying each step. About **2 minutes**. |
| Re-running the same image | **Changes nothing**: the duplicate guard (1.2.1) finds the booked Order + Invoice, verifies them and finishes "already processed" in a few seconds. |
| New order of a known customer | Selects the existing Debtor, Products, VAT and payment method (no duplicates), books a new Order + Invoice. Tested on the in-memory Fakturama. |
| Extraction (Gemini) | Live calls verified; outputs validated arithmetically before Fakturama is touched. |
| Every manual-review stop | Tested on the in-memory Fakturama (`tests/workflow`). |

## Setup

1. Windows 10/11, Python 3.12, Fakturama **2.2.0** (`C:\Program Files\Fakturama2`).
2. Start Fakturama once and finish its first-run setup (workspace `C:\fakturama`, English UI). The app's
   en_US formats (`Nov 6, 2026`, `$0.00`) are configured in `config/settings.yaml`.
3. Install:
   ```bash
   python -m venv .venv
   .venv\Scripts\python -m pip install -e ".[dev]"
   ```
4. Copy `.env.example` to `.env` and set `GEMINI_API_KEY` (Google AI Studio). The model is
   `extraction.model` in `config/settings.yaml` (default `gemini-flash-latest`, with fallbacks).

## Run

```bash
imagetocash run samples/order-page3.png             # the full flow 1.1 -> 5.7
imagetocash extract samples/order-page3.png         # spec 1.1-1.2 only, values masked
imagetocash run samples/order-page3.png --from-json runs/<ts>/extracted.json   # replay, no LLM call
imagetocash inspect --out runs/ui-tree.txt          # dump Fakturama's UIA tree for control mapping
imagetocash reset-workspace --yes                   # test runs: restore the clean database (moves, never deletes)
```

**Exit codes:** `0` Order + Invoice saved and verified, or already processed · `2` stopped for manual
review (spec step + reason) · `1` unexpected error.

**Each run writes `runs/<timestamp>/`** (git-ignored, contains order data):
- `run.log`: one JSON line per step, values masked;
- `steps.jsonl`: expected / observed / result / seconds per spec step;
- `stage_N.png` after each stage and `NN_<step>_failed.png` on a stop;
- `report.md`;
- `extracted.json`.

The console shows one line per step, with values masked as `N***H (21 chars)`.

**Re-runs never book an order twice.** Before step 1.3 creates anything, step 1.2.1 searches Data >
Documents for the image's External Reference. This is a read-only addition to the spec:

| Found for this Cust.Ref. | Result |
|---|---|
| nothing | book it (1.3 → 5.7) |
| one Order + one Invoice matching total, customer and states | "already processed", exit 0, nothing changed |
| anything else (Order without Invoice, two Orders, another total, unpaid Invoice for a PAID order) | manual review, nothing changed |

## How it works

```
cli ─▶ workflow (guard + stages 1-5 = spec sections) ─▶ domain (pricing, validation, matching; pure)
          ├─▶ fakturama (screen objects, workbench, tables, selectors.yaml) ─▶ automation (UIA, OCR, evidence)
          └─▶ extraction (Gemini vision, parsing) ─▶ domain
```

- **One stage per spec section** (`workflow/stage1_open_order.py` … `stage5_invoice.py`); every action and
  check runs inside `evidence.spec_step("2.10.4", …)`. Stages depend only on `workflow/protocols.py`, so
  the whole flow is tested against an in-memory Fakturama (`tests/workflow/fakes.py`).
- **One decision rule** for Debtor (2.3), payment method (2.10.2), Product (3.3) and VAT (3.5)
  (`workflow/resolver.py`):
  - exactly one exact row → use it;
  - several → stop (ambiguous);
  - only near-misses → stop (conflicting);
  - nothing → create, then require it to be selectable exactly once.
- **Grounding, in order:**
  1. UIA properties.
  2. Label anchor (SWT fields are unnamed; their label is a sibling).
  3. Position inside a labeled group ("upper icon beside Addresses").
  4. Lists (NatTable) are read with their own copy binding; OCR inside the list's UIA rectangle is the fallback.

  All names live in `config/selectors.yaml`. The single pointer exception (double-click on a dialog row) is documented in `fakturama/row_choice.py`.
- **Money is `Decimal`.** The LLM returns amounts as printed strings. Code parses them and checks every line, the totals and the payment date **before Fakturama is touched**.
- **Verify every step.** Fields are typed (so Fakturama's own listeners run, as for a person), read back, retried once, then stopped for review. Everything Fakturama does that is not obvious is in [docs/control-map.md](docs/control-map.md), under Gotchas.
- **Fast without skipping checks.** An editor's tab and pane are kept once found, named lookups stop at the first match, and the verified Items line is returned instead of re-read.

Design rationale and trade-offs: [docs/design-doc.md](docs/design-doc.md). Flow diagram:
[docs/image-to-cash-plan.html](docs/image-to-cash-plan.html).

## Tests

```bash
.venv\Scripts\python -m pytest          # 73 tests, no Fakturama or network needed
.venv\Scripts\ruff check src tests
.venv\Scripts\python -m mypy src
```

## Not done / next steps

1. **Partial earlier work is not resumed.** An Order without its Invoice (e.g. a run stopped at 4.6) stops for manual review instead of finishing the Invoice. Resuming would need to open an existing document from the Documents list, which only works by double-click.
2. **VAT code of a pre-existing rate is not opened** (3.5). The list has no code column and a row opens only by double-click, so an existing `VAT 19%` is matched on Name + Value and the gap is logged. Rates the script creates always get code S.
3. **Order-level discount / shipping from the image** (4.2) stops for review instead of being set.
4. **The selection-dialog row choice** is a double-click at a point measured inside the list element (the one pointer exception).
5. Live runs so far: Fakturama 2.2.0, en_US, one machine (maximized window on 1920×1080 and 2560×1440
   screens). Other window sizes and scaling factors are not yet verified live.

## Written question

**If you had 3 more hours, what would you do?**

1. **Resume instead of stop** (≈1.5 h): finish a partially booked order. Open the existing Order from Documents to create its missing Invoice, or open an unpaid Invoice to mark it paid, with the same checks as a fresh run.
2. **Prove robustness** (≈45 min): run the sample at another window size and scaling, plus two more order images (one with an identical delivery address, one unpaid), and keep their evidence as regression fixtures.
3. **Golden tests for the readers** (≈45 min): recorded NatTable copies and screenshots as fixtures for the list reader and the OCR fallback, so Fakturama-format changes fail in CI instead of live.
