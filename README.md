# Fakturama Image-to-Cash

Turns one order image into a saved, verified **Order** and linked **Invoice** in the Fakturama desktop
app, following the take-home spec step by step (1.1 → 5.7). It uses **Microsoft UI Automation** to
drive the app, **Windows OCR** for widgets UIA cannot see into, and **Claude vision** to read the image.
No hardcoded coordinates: every click target comes from UIA or from OCR inside a UIA rectangle.

## Status (be honest about what is proven)

| Part | State |
|---|---|
| Extraction (1.1–1.2): Claude vision → typed, validated order | Built and unit-tested on the page-3 sample via a recorded extraction. **Live Claude call not yet run** (needs `ANTHROPIC_API_KEY`). |
| Spec logic 1.1 → 5.7 (select / create-then-reselect / every manual-review stop) | Built and **tested end to end** against an in-memory Fakturama (`tests/workflow`). |
| Fakturama controls for every screen in the flow | **Mapped live** (`docs/control-map.md`, `config/selectors.yaml`), including the separate delivery address (2.8) and the payment fields (5.3). |
| Date fields (Nebula CDateTime) | **Verified live**: `Jul 14, 2026`, `Jan 31`, `Feb 29, 2024` set and committed. |
| Debtor combo selection, typed fields with read-back, VAT row code lookup | **Verified live** on individual screens. |
| **One full live run 1.1 → 5.7** | **Not done yet.** |

## Setup

1. Windows 10/11, Python 3.12, Fakturama **2.2.0** (`C:\Program Files\Fakturama2`).
2. Start Fakturama once and finish its first-run setup (workspace folder, English UI). The app uses its
   en_US formats (`Nov 6, 2026`, `$0.00`); change `config/settings.yaml` if yours differ.
3. Install:
   ```bash
   python -m venv .venv
   .venv\Scripts\python -m pip install -e ".[dev]"
   ```
4. Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY`.
5. Optional for control mapping: [Accessibility Insights for Windows](https://accessibilityinsights.io).

## Run

```bash
imagetocash extract samples/order-page3.png        # spec 1.1-1.2 only: JSON + VALID / MANUAL REVIEW
imagetocash run samples/order-page3.png            # the full flow 1.1 -> 5.7
imagetocash run samples/order-page3.png --from-json tests/fixtures/northstar_extracted.json  # no LLM call
imagetocash inspect --out runs/ui-tree.txt         # dump Fakturama's UIA tree for control mapping
```

Exit codes: `0` Order + Invoice saved and verified · `2` stopped for manual review (with the spec step and
reason) · `1` unexpected error. Every run writes `runs/<timestamp>/`: `extracted.json`, `steps.jsonl` (one
line per spec step: expected, observed, result), `NN_<spec-step>.png` screenshots and `report.md`.

## How it works

```
cli ─▶ workflow (stages 1-5 = spec sections, runner) ─▶ domain (pricing, validation, matching; pure)
          ├─▶ fakturama (screen objects + selectors.yaml) ─▶ automation (UIA session, locators, OCR, evidence)
          └─▶ extraction (Claude vision, parsing)        ─▶ domain
```

- **One stage per spec section.** `workflow/stage1_open_order.py` … `stage5_invoice.py` call the UI in the
  spec's order, and every action and check is wrapped in `evidence.spec_step("2.10.4", …)`.
- **One decision rule** for Debtor (2.3), payment method (2.10.2), Product (3.3) and VAT (3.5)
  (`workflow/resolver.py`): exactly one exact row → use it; several → stop (ambiguous); only near-misses →
  stop (conflicting); nothing → create, then require it to be selectable exactly once.
- **Grounding, in order:** UIA properties → label anchor (SWT fields are unnamed; their label is a sibling)
  → position inside a labeled group ("upper icon beside Addresses") → OCR inside the UIA rectangle for
  custom-drawn NatTable lists. Selectors live in `config/selectors.yaml`.
- **Money is `Decimal`.** The LLM returns amounts as printed strings; code parses them and checks every
  line, the net/VAT/gross totals and the payment date **before Fakturama is touched**.
- **Verify every step:** fields are typed (so SWT recalculates as for a human), read back, retried once,
  then stopped for review.
- **Only parallel part:** Fakturama's JVM boots while Claude reads the image. Everything after is
  sequential, because the spec orders it and there is one UI.

Design rationale and trade-offs: [docs/design-doc.md](docs/design-doc.md). Control discovery:
[docs/control-map.md](docs/control-map.md). Flow diagram: [docs/image-to-cash-plan.html](docs/image-to-cash-plan.html).

## Tests

```bash
.venv\Scripts\python -m pytest          # 47 tests, no Fakturama or network needed
.venv\Scripts\ruff check src tests
.venv\Scripts\python -m mypy
```

## Not done / next steps

1. **One full live run** against a clean workspace, then a second run (select branches), with the
   recording and annotated screenshots for the deliverable.
2. **Items grid editing (3.13–3.15)**: OCR column positions plus double-click editing on the NatTable;
   the grid has not been seen with data yet, so its column titles and edit gesture still need a live check.
3. **OCR of empty-looking cells**: single digits (e.g. `0` in *Net Days*) can be missed by Windows OCR; the
   flow does not depend on those columns, but rows are read twice for stability.
4. Order-level discount / shipping from the image (4.2) stops for review instead of being set.
5. No duplicate-order guard: running the same image twice creates a second Order and Invoice, as the spec
   does not ask for one.

## Written question

**If you had 3 more hours, what would you do?**

1. **Finish calibration and get one fully green live run** (≈1.5 h): map the remaining dialogs and editors
   with `inspect`, fix `selectors.yaml`, implement the second (delivery) address, and confirm the
   NatTable edit gesture. Then record the run for the deliverable.
2. **Make OCR reads trustworthy** (≈45 min): read every list twice and require agreement; add a second-pass
   crop per cell for SKUs and amounts; log OCR confidence; add golden screenshots as regression tests for
   the OCR table reader.
3. **Resilience** (≈45 min): a checkpoint file per run so a crash mid-flow resumes at the right spec step
   instead of re-creating master data; a pre-run guard that stops if an Order with the same Cust.Ref.
   already exists; a "dry run" mode that only reads and reports what would be created.
