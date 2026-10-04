# Outputs: screen, redline and mandate fit

Two documents built from a finding ledger, alongside the screen report (`pfia report`).
Both read the ledger and the register only, never the policy file, so they show exactly what
the review found.

| Output | Audience | Command |
|---|---|---|
| **Screen**: the review result and the internal working paper | Internal; page one written to be shareable | `pfia report` |
| **Redline**: proposed amendments with a draft resolution | Governing body, after reviewer approval | `pfia redline` |
| **Mandate fit**: can a strategy run under the policy? | Internal onboarding only | `pfia mandate-fit` |

## 1. Produce the ledger

```bash
pfia extract --profile engagements/<client>/profile.json --policy engagements/<client>/policy.pdf \
    --cache engagements/<client>/cache --out engagements/<client>/extraction.json
pfia review --profile engagements/<client>/profile.json --policy engagements/<client>/policy.pdf \
    --extraction engagements/<client>/extraction.json --schedule-b-v2 \
    --out engagements/<client>/ledger.json
```

`--schedule-b-v2` matters for both outputs: it records the authorized-investment terms
condition by condition (CP-03, POL-10 and so on), which the redline names and mandate fit
compares. Without it the redline falls back to the 0.18.0 instrument schedule and mandate fit
compares authorization only.

The extraction file records which reader produced it (`_extraction.adapter`). An extraction
from the offline reader, or a file without that record (made before 0.20.0), is treated as
not review-grade: its findings are queued for verification, and the redline holds them rather
than proposing language. Re-run `pfia extract` with Gemini for a review-grade ledger.

## 2. Screen

```bash
pfia report --ledger engagements/<client>/ledger.json --entity "Harris County" \
    --entity-class "County" --out engagements/<client>/screen.pdf
```

Page one: the result, a tile per section (authorized investments, investment management
provisions, governance summary), the scope statement and the leading items. The working paper
follows: work queue, authorized investments condition by condition, Core provisions element by
element with proposed language, governance summary, restatement items, evidence requests and
provenance. `--distribution client-draft` marks page one as a draft pending review.

**Reliability banner.** If extraction quality is not OK, or no enumerated list of authorized
investments was located, page one says so in red, and so do the redline and mandate fit. Treat
authorized-investment results as provisional until the policy is re-read with pypdf or
pdftotext.

## 3. Redline

```bash
pfia redline --ledger engagements/<client>/ledger.json --entity "City of Richardson" \
    --html engagements/<client>/redline.html --out engagements/<client>/redline.pdf
```

What it contains, and the rules that decide it:

| Part | Rule |
|---|---|
| Amendments | Core Schedule A provisions that conflict with the Act, are not expressly addressed, or are addressed in part (statutory band), plus authorized-investment terms that conflict with the Act. Revisions first, then additions |
| Optional restatements | Core provisions in the advisory band (the Act binds them regardless), such as the quarterly report. Leave out with `--statutory-only` |
| Held for verification | Findings whose reading needs checking (a discarded quote, or an offline reader), and authorized-investment conditions the reader could not settle. No language is proposed for them |
| Never included | Context (governance) provisions, advisory items outside Core, instruments outside the client base |
| Draft resolution | Adopts the amendments and records the annual review Sec. 2256.005(e) requires |

Proposed text comes from the register's `proposed_text` (statute wording for each Core
control) or, for authorized investments, the condition's requirement. `[Entity]` is filled
with the entity name; other brackets are for the entity to complete and are counted as
decisions. The review records where conflicting text appears, not where new text belongs, so
the drafter places each insertion.

## 4. Mandate fit

```bash
cp data/mandates/policy-limits.example.json engagements/<client>/policy_limits.json   # edit the figures
pfia mandate-fit --ledger engagements/<client>/ledger.json \
    --strategy data/mandates/short-term-government-credit.example.json \
    --policy-limits engagements/<client>/policy_limits.json \
    --entity "City of Richardson" --out engagements/<client>/mandate-fit.pdf
```

**Strategy file** (one per strategy, maintained by the firm; see the example): instrument
codes and condition IDs from `data/registers/instrument-conditions/register.json`, each with
the strategy's own value. The command rejects an unknown or retired condition.

```json
"COMMERCIAL_PAPER": {"summary": "A-1/P-1, two agencies, to 270 days", "target": "up to 20%",
  "terms": {"CP-01": {"value": 270, "unit": "days"}, "CP-02": "A-1", "CP-03": ["TWO_AGENCIES"]}}
```

**Layout.** Page one: the result tiles, the **Investment Policy Summary** (blocks,
constraints, readings to confirm, and "fit is not compliance" notes), then the
**Portfolio-level parameters**. Page two: the **Authorized Investment Review**, instrument by
instrument, followed by how the comparison is made.

**How the fit is decided.** For each condition the ledger records the **binding** term: the
stricter of the policy and the Act, or the Act's term where the policy is silent or conflicts.
The strategy's value is compared with it by the evaluator's own comparators.

| Fit | Meaning |
|---|---|
| Blocks | The strategy uses an instrument the policy does not authorize |
| Constrains | The binding term is narrower than the strategy's (for example the policy caps CP at 180 days) |
| Fits | The strategy runs as designed |
| Cannot determine | The policy's term could not be read with certainty |
| Not used / Not reviewed | The policy permits something the strategy does not use / outside the client base |

Portfolio-wide limits (maximum maturity, weighted average maturity, settlement) are not yet
extracted; a reviewer enters the policy's figures in the policy limits file, and the rows say
"Entered by reviewer". Units must match to compare.

"Fit is not compliance": where the policy's terms conflict with the Act but the strategy meets
the Act, the note says trading is unaffected and the clause belongs in the redline.

## 5. Examples for the team

```bash
python3 scripts/make_output_examples.py --out build/examples
```

Runs the pipeline offline on two synthetic policies (a deficient city policy and a largely
conforming water authority policy) and writes the ledger, redline and mandate fit for each, as
HTML and, with WeasyPrint, PDF. Every page is marked "Example · synthetic policy, offline
reader"; the offline reading is treated as review-grade for layout purposes only.

## Templates

`src/pfia/report/templates/redline.html`, `mandate_fit.html` and the shared `outputs.css`
(the screen report's design tokens). The view data comes from `src/pfia/report/outputs.py`
(`redline_context`, `mandate_fit_context`). Templates render under Jinja2's StrictUndefined,
so a missing field is an error, not a silently blank cell.
