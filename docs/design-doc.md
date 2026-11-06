# Design: Fakturama Image-to-Cash automation

## 1. Goal and scope

Turn one order image into a saved, verified Order and its linked Invoice inside Fakturama, following the
specified Order-first flow exactly: the Order's own Debtor and Product selectors are the existence checks,
missing master data is created only when no exact match exists, and every step is verified before the
next. In scope: one image, one run, the steps in the spec (1.1 → 5.7). Out of scope: Delivery, Correction
and Dunning documents, batch processing, and any direct database access. Fakturama is driven only
through its UI, like a person would.

## 2. Architecture

Five layers, with dependencies pointing inward:

- **Domain** (pure, no I/O): order model, money rules (gross master price, line price), the pre-UI
  consistency check, and the exact-match rules for Debtor, Product, VAT and payment method.
- **Extraction:** image → structured order through Gemini vision (Google AI Studio), then deterministic parsing.
- **Workflow:** five stages that mirror the spec's five sections, plus a runner. Stages talk only to small
  per-screen interfaces, so all decision logic is testable without the app.
- **Fakturama adapters:** one screen object per Fakturama screen. Element selectors live in a config file.
- **Automation core:** app-agnostic UIA session, locators, waits, input with read-back, OCR, evidence.

Each spec step is one call plus one verification, recorded with its spec number, the expected and observed
values and a screenshot. A run ends in one of three states: **done**, **manual review** (a deliberate stop
naming the spec step and the reason), or **error**.

## 3. Control discovery and grounding

Discovery on Fakturama 2.2.0 showed three kinds of controls:

1. **Native SWT controls** (toolbar buttons, text fields, combos, tabs) are fully visible to UIA. Toolbar
   buttons carry their tooltip as a name with an Invoke pattern ("Create: New Order", "Save the current
   contents"). Most text fields expose a Value pattern, but many have **no name**: their label is a
   separate sibling text element.
2. **Unnamed icons** (the "select existing contact" and the green "+" beside Addresses) are image elements
   with no name and no Invoke pattern.
3. **Custom-drawn widgets** (Nebula NatTable lists and grids, the CDateTime date field) appear as one
   opaque pane with no children.

The grounding strategy follows from this. Locators are tried in order, and each one searches only inside
the current editor or dialog:

1. **By UIA properties:** control type, name, automation id.
2. **By label anchor:** find the label text, take the next field of the wanted type in tree order.
3. **By order inside a labeled group:** "the upper icon beside Addresses" = the first image, top to bottom,
   in the Addresses label's container. This is how the spec itself describes the controls.
4. **By OCR inside a UIA rectangle:** for custom-drawn lists, capture only the rectangle UIA reports, run
   Windows OCR, build columns from the header row, and click rows at the positions OCR measured. A
   vision-model locator exists as a last resort and is off by default.

No coordinate is ever written in code or config; every click point comes from UIA or from OCR at
runtime. Labels and names live in a selector file, so a UI change is a config edit. The session addresses
the main window by handle and restores it when minimized, because criteria-based lookups miss minimized
SWT windows.

Waits are explicit: poll for a condition with a timeout, never a fixed sleep. "List stabilized" (2.2) means
two consecutive identical reads.

## 4. Image extraction

- **Gemini vision with a response schema.** One request returns a schema-typed object that mirrors spec
  1.2. The model is told to copy values exactly as printed and to use null rather than invent.
- **Numbers are code's job, not the model's.** Amounts, percentages and dates come back as printed strings
  and are parsed deterministically to `Decimal` and dates.
- **Validation before any UI action:** every line total = qty × unit net × (1 − discount); lines sum to
  the net total; VAT per rate; net + VAT = gross; PAID requires a payment date. Any inconsistency stops
  the run at 1.1, before Fakturama is touched.
- A saved extraction can be replayed, so the UI flow can be developed without paying for repeated calls.

## 5. Matching rules and when to stop

- **Exact match** means all spec fields are equal after normalization: Debtor = Company, First Name,
  Name, ZIP, City; Product = SKU; VAT = name `VAT n%`, value n and code S; payment method = name.
- **Ambiguous** (several exact rows) and **conflicting** (same identity, different checked field, e.g. the
  same company in another city, or `VAT 19%` with code Z) both **stop for manual review**. Only "nothing
  related" leads to creation. This follows "when in doubt, skip": creating a near-duplicate is worse than
  stopping.
- After creating a record, it must be selectable exactly once from the same place the spec checks
  (2.12, 3.12), otherwise stop.
- OCR text is compared with a confusable-tolerant normalization (O/0, I/l/1). Windows OCR read
  `CHR-ERG-01` as `CHR-ERG-OI` during testing.

## 6. Verification and evidence

Every field is typed rather than set programmatically, so SWT's own listeners recalculate as for a
human. It is then read back, retried once, and stopped on mismatch. Line prices, totals, the Documents
rows (found by the generated document number), the follow-up link and the paid state are checked against
the source. Each run leaves a JSON log per spec step, numbered screenshots and a report, which double as
the annotated-screenshot deliverable.

## 7. Trade-offs

| Choice | Benefit | Cost / risk |
|---|---|---|
| UIA first, OCR only inside UIA rectangles | Meets "no coordinates"; fast; deterministic where UIA works | OCR misreads; mitigated by tolerant matching, stable-read waits and read-back |
| Python + pywinauto (UIA backend) | Fast to build; same API surface as Microsoft UIA | Slower than raw COM; mitigated by scoped searches |
| LLM for extraction, code for numbers | Robust to any layout; arithmetic checks catch model errors | API cost and latency; data leaves the machine; replay mode for development |
| Spec-literal flow through selectors | Matches the task; mirrors how a technician works | Slower than querying the database, which is deliberately not used |
| Stop rather than guess | Safe; every stop is explained and traceable | Some runs end early by design |
| Keyboard and typing over programmatic set | App logic runs exactly as for a user | Depends on focus; the session forces the window to the front |

## 8. Risks and what is left

The custom-drawn grid editing gesture, the date widget's typed input, and the second-address UI for a
separate delivery address are the largest unknowns; each is isolated in one screen object and fails into a
clear manual-review stop rather than a wrong record.
