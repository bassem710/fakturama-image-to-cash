# Fakturama Image-to-Cash automation (TJM Labs take-home)

Turn one order image into a saved, verified Order and linked Invoice inside the Fakturama desktop app, driving its UI with Microsoft UI Automation (UIA). The full spec is `Take home project 2026.pdf` on the Desktop; when this file and the spec disagree, the spec wins.

## Hard rules (never break)

- **No hardcoded coordinates and no fixed UI layout.** Find every control through UIA by `Name`, `ControlType`, `AutomationId` or `ClassName`, scoped to the active window or editor. Never `click(x, y)` with literal numbers.
- **Follow the spec's order of operations exactly:** Order first; the Order's Debtor and Product selectors are the existence checks; create master data only when no exact match exists, then go back to the same open Order and select it.
- **Never use the green `+` (new) icons on the Order** for Debtor or Product selection. Use the upper "select existing" icons.
- **Create the Invoice only from the saved Order's "Create a follow-up document" area,** never from the top toolbar.
- **Stop for manual review on ambiguity.** Multiple or conflicting matches, totals that don't add up, a missing payment method on the Invoice, or a created record that doesn't reappear in its selector → stop, log why, take a screenshot, exit non-zero. Never guess.
- **Never invent data.** If the image lacks a value, leave the field at its default. Only mark an Invoice paid when the extracted status is PAID, using the extracted payment date and the full Invoice total.
- **Safe to re-run:** a second run must not create duplicate Debtors, Products, VAT rates or payment methods.
- **Click Save once** per editor, as the spec says.

## Money and data

- Use `decimal.Decimal` for every amount; never `float`. Round to 2 places with `ROUND_HALF_UP`.
- Product master gross price = unit net × (1 + VAT/100). Do not apply the line discount to it.
- Line price = qty × unit net × (1 − discount/100).
- Validate extracted data before touching the UI: each line total, net total, VAT total and gross total must add up.
- Normalize dates and decimal separators (`1.234,56` vs `1,234.56`) explicitly; keep the raw string in logs for debugging.

## Automation conventions

- Every UI step follows **precondition → action → verify → on failure (retry once, else manual review)**. After setting a field, read the value back and compare.
- Use explicit waits (element exists, is enabled, list stopped changing, dialog closed) with timeouts. No bare `time.sleep` except tiny polling intervals inside a wait helper.
- Grounding fallback order: UIA patterns (`Invoke`, `Value`, `SelectionItem`, `ExpandCollapse`, `Toggle`, `Grid`) → keyboard shortcuts / focus navigation → OCR or vision only inside an element rectangle obtained from UIA.
- Fakturama is an Eclipse RCP/SWT app. Before automating a new control, inspect it (`imagetocash inspect` or Accessibility Insights; Inspect.exe is not installed on this machine) and record it in `docs/control-map.md` and `config/selectors.yaml`.
- Never search from the desktop root, and address the main window by handle: criteria lookups miss a minimized SWT window.
- Take a screenshot after each major step into `runs/<timestamp>/` with a step-numbered filename.

## Code style

- Python 3.12, type hints, small modules under `src/imagetocash/`: `domain/` (pure rules), `extraction/` (Claude vision + parsing), `automation/` (app-agnostic UIA/OCR), `fakturama/` (screen objects), `workflow/` (one stage module per spec section), `cli/`.
- Workflow stages depend only on the protocols in `workflow/protocols.py`; new UI behavior goes into a screen object, new rules into `domain/`.
- Every UI element is named in `config/selectors.yaml`, not in code.
- Run `ruff check`, `mypy` and `pytest` before committing.
- Pydantic models for the extracted order. Configuration (paths, timeouts, model name) in a config file or env vars; never commit API keys.
- Keep it simple: smallest code that meets the spec. No speculative abstractions.
- Unit-test extraction validation and price math with `pytest`; these tests must not need Fakturama running.

## Logging and privacy

- Structured logs per step: step id, action, expected value, observed value, result.
- Treat order data like patient data at TJM: don't send it anywhere except the chosen extraction model, and don't print API keys.

## Working with Claude in this repo

- Before writing code for a new stage, restate the spec steps for that stage and the verification you'll do.
- When a step is skipped or stubbed for time, add it to the README "Not done / next steps" section in the same change.
- Prefer finishing a thin end-to-end path over perfecting one stage.
