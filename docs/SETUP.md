# Setup and first run

For a fresh checkout of release 0.21.0 on macOS (Linux is the same apart from the Homebrew
lines). Every step says what success looks like, so when something breaks you know which
step to report.

The model is **Gemini 3.8 Flash** (`gemini-3.8-flash`). Steps 1 to 7 need no model, no
network and no install. Step 8 adds the model; step 10 the PDF report.

---

## Step 1 - Unpack and enter the repository

```bash
tar -xzf policy_health_screen_rebuild-0.21.0.tar.gz
cd policy_health_screen_rebuild
git log --oneline -1
```

**Expect** the 0.21.0 commit, and in `ls`: `pyproject.toml`, `src`, `data`, `tests`,
`Makefile`, `bakeoff.gemini-flash.example.json`, `.env.example`.

## Step 2 - Check Python and the version

```bash
python3 -V                                        # 3.11 or later
PYTHONPATH=src python3 -m pfia version | head -1
```

**Expect** `tx-pfia-register 0.21.0`. If Python is older: `brew install python@3.12` and use
`python3.12` everywhere below.

## Step 3 - Prove the tree is intact

```bash
make test             # unit and integration tests
make golden           # seven pinned end-to-end cases
make verify           # every control's statute text against the committed snapshot
make statute-rebuild  # the snapshot reproduces from the pinned raw HTML
```

**Expect** `Ran 384 tests ... OK (skipped=1)`, seven `ok` lines, `all control source texts are
in force as written`, and `snapshot reproduces from data/sources/raw/GV.2256.2026-09-27.htm`.

If any of these fails, stop and send the output. Everything downstream depends on them.

## Step 4 - Look at the register

```bash
make coverage-map      # which sections of the statute carry controls
make audit             # authoring report
make schema            # every register against its schema (needs: pip install jsonschema)
make export-review     # reviewer CSV and workbook under build/review/
```

**Expect** every testable section of Subchapter A covered; `11 authoring gap(s)`, which is
expected (seven controls had their anti-pattern libraries emptied on purpose in the
2026-09-27 element audit); and five `ok` schema lines.

## Step 5 - Run a review on a synthetic policy

```bash
make review
```

**Expect** three sections in this order, and a ledger at `build/ledger.json`:

```
Authorized investments: REVISIONS_RECOMMENDED
Investment management provisions: ADDRESSES_PROVISIONS_REVIEWED
Policy governance (summary): SUMMARIZED
```

There is no score. A section's status is set by fixed rules on the items beneath it
(`docs/METHODOLOGY.md`, section 7). This run uses the offline keyword extractor, so it shows
the pipeline working, not review-grade reading.

## Step 6 - Install (optional)

Without it, every command is `PYTHONPATH=src python3 -m pfia ...`; the `make` targets set the
path themselves.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools
pip install -e '.[dev,pdf]'      # jsonschema for `make schema`; pypdf for reliable PDF text
pfia version | head -1
```

| Message | Fix |
|---|---|
| `build backend is missing the 'build_editable' hook` | `python -m pip install --upgrade pip setuptools`, retry |
| `error: externally-managed-environment` | Activate the venv first |
| `No matching distribution found` | No network from the venv: skip this step |

Commands below are written as `pfia ...`. Use `PYTHONPATH=src python3 -m pfia ...` if you
skipped this step.

---

## Step 7 - Prepare a real policy (still offline)

Client documents go under `engagements/`, which git ignores, and nowhere else.

```bash
mkdir -p engagements/example
cp /path/to/policy.pdf engagements/example/policy.pdf

pfia ingest --policy engagements/example/policy.pdf
pfia instruments --policy engagements/example/policy.pdf
pfia profile init --entity "Example Regional Water Authority" --out engagements/example/profile.json
# answer every question in the file, then:
pfia profile check --profile engagements/example/profile.json
```

- `ingest`: `quality.verdict` is `OK` and `backend` is `pypdf` or `pdftotext`. The built-in
  `stdlib-pdf` reader is a floor: on some word-processor PDFs it splits words ("q uarter ly"),
  which makes instruments look unauthorized. Install pypdf (`pip install pypdf`) or poppler
  (`brew install poppler`). A `DEGRADED` verdict names the cause and the remedy. Check also that
  the page count is right. `UNUSABLE` means a scanned
  policy; it is refused rather than reviewed and needs OCR first.
- `instruments`: `state` should be `enumerated`, and `authorized` should match what a reader
  would say the policy authorizes. A missing type is a gap in
  `data/registers/instrument_lexicon.json`.
- `profile check`: `18 answered, 0 unanswered` (17 questions plus the entity classes). It exits
  non-zero until complete, because an unanswered question leaves dependent controls
  unresolved and their section then reads REVIEW_IN_PROGRESS.

**Filling in the profile.** `profile init` writes a JSON file; `_how_to_answer` inside it
repeats these rules.

| Field | Answer with | Example |
|---|---|---|
| `classes` | A list of IDs from `_entity_classes` in the same file. Parent classes are added automatically | `"classes": ["MUNICIPALITY"]` for a city such as the City of Richardson |
| Yes/no questions | `true` or `false`, without quotes | `"has_pooled_fund_groups": true` |
| Amounts and counts | A plain number | `"long_term_debt_principal": 250000000` |
| Not known | `null` | The dependent controls are reported as unresolved, never guessed |

`profile check` accepts unambiguous everyday forms and says so (`"yes"` becomes `true`,
`"$250,000,000"` becomes `250000000`, `"municipality"` becomes `MUNICIPALITY`). Anything it
cannot read with certainty, such as `"maybe"` for a yes/no question or `"y"` in `classes`, is
refused with a message naming the field, never guessed, because a quoted `"no"` would otherwise
count as true.

## Step 8 - Connect Gemini 3.8 Flash

```bash
cp .env.example .env
# edit .env: set GEMINI_API_KEY; keep PFIA_ADAPTER=gemini and PFIA_MODEL=gemini-3.8-flash
set -a; source .env; set +a
pfia adapter-check --adapter gemini --model gemini-3.8-flash --show-prompt
```

**Expect** `Response shape parsed and at least one quote verified against the document.` A
failure is a key, quota or response-shape problem, never a judgement call; the error carries
Google's own message (for example `INVALID_ARGUMENT: ...` or `RESOURCE_EXHAUSTED: ...`).

| `.env` variable | Value | Why |
|---|---|---|
| `PFIA_ADAPTER`, `PFIA_MODEL` | `gemini`, `gemini-3.8-flash` | Used whenever `--adapter` / `--model` are omitted |
| `PFIA_GEMINI_THINKING_LEVEL` | `low`, `medium` (default) or `high` | Reasoning effort; `minimal` is not supported on 3.8 Flash. Chosen by the bake-off |
| `PFIA_GEMINI_MAX_OUTPUT_TOKENS` | `32768` | Thinking tokens count against the ceiling |
| `PFIA_HTTP_RETRIES` | `4` | Retries on 429 and 5xx, honouring Retry-After |

Temperature is never sent to Gemini 3.x models, following Google's guidance.

## Step 9 - Review the policy with the model

```bash
pfia extract --profile engagements/example/profile.json \
    --policy engagements/example/policy.pdf \
    --cache engagements/example/cache \
    --out engagements/example/extraction.json

pfia review --profile engagements/example/profile.json \
    --policy engagements/example/policy.pdf \
    --extraction engagements/example/extraction.json \
    --schedule-b-v2 \
    --out engagements/example/ledger.json
```

- `extract` sends each **Core** control to Gemini. **Context** controls are answered offline and
  never reach the model (ADR 0011); the run summary says how many.
- `review --schedule-b-v2` also runs the authorized-investment condition catalogue through
  Gemini and records it in the ledger as `instrument_conditions`. The catalogue is
  **proposed**: it is reported and never changes a section status until it is adopted.

## Step 10 - The report

```bash
pip install jinja2
pfia report --ledger engagements/example/ledger.json \
    --entity "Example Regional Water Authority" \
    --entity-class "Water district (Water Code ch. 49)" \
    --html engagements/example/report.html
```

PDF additionally needs WeasyPrint and its Homebrew libraries:

```bash
brew install pango gdk-pixbuf libffi
pip install -e '.[report]'
pfia report --ledger engagements/example/ledger.json \
    --entity "Example Regional Water Authority" \
    --entity-class "Water district (Water Code ch. 49)" \
    --out engagements/example/report.pdf
```

Missing libraries show as `cannot load library 'libgobject-2.0-0'` at import.

## Step 11 - Clean up

```bash
pfia purge engagements/example/cache --yes
```

Ledgers and reports are the artifacts meant to survive. The cache holds verbatim policy text.

---

## Cheat sheet

| Goal | Command |
|---|---|
| Prove the tree is intact | `make test && make golden && make verify` |
| Register coverage | `make coverage-map` |
| Reviewer workbook | `make export-review` |
| Read a PDF | `pfia ingest --policy X.pdf` |
| What it authorizes | `pfia instruments --policy X.pdf` |
| Entity profile | `pfia profile init --entity "..." --out P.json`, then `pfia profile check --profile P.json` |
| Smoke-test Gemini | `pfia adapter-check --adapter gemini --model gemini-3.8-flash` |
| Extract with Gemini | `pfia extract --profile P.json --policy X.pdf --cache C --out E.json` |
| Review | `pfia review --profile P.json --policy X.pdf --extraction E.json --schedule-b-v2 --out L.json` |
| Review, fully offline | `pfia review --profile P.json --policy X.pdf --out L.json` |
| Render the report | `pfia report --ledger L.json --entity "..." --out R.pdf` |
| Redline (draft amendments) | `pfia redline --ledger L.json --entity "..." --out redline.pdf` |
| Mandate fit (internal) | `pfia mandate-fit --ledger L.json --strategy S.json --policy-limits P.json --entity "..." --out fit.pdf` |
| Team examples of both | `python3 scripts/make_output_examples.py` |
| Choose the thinking level | `docs/MODEL-RUNBOOK.md` |
| Benchmark against prior reviews | `docs/RUNBOOK.md` |
| Delete derived client data | `pfia purge <dir> --yes` |
