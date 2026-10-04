# Model runbook: Gemini 3.8 Flash

How to configure the model, choose its thinking level against reviewed ground truth, record
the run every later step replays, and use it on an engagement. Everything runs on your
machine (VS Code terminal or shell). Keys stay in `.env`; results, caches and cassettes
contain verbatim policy text and are git-ignored.

## What the model does, and does not do

The model reads short passages and returns facts with verbatim quotes: a figure and its
unit, a rating and how many agencies, which statutory alternatives a clause takes, and
whether a Core element is addressed. It never decides conformity; code compares every fact
against the statute. A quote that cannot be found in the document is discarded and its
condition reads UNKNOWN, never a pass or a conflict. Context controls never reach the model
(ADR 0011). PDF text extraction uses no model (ADR 0003).

## 1. Configure

```bash
cp .env.example .env
#   GEMINI_API_KEY=...            (Google AI Studio or Vertex, paid tier)
#   PFIA_ADAPTER=gemini
#   PFIA_MODEL=gemini-3.8-flash
#   PFIA_GEMINI_THINKING_LEVEL=medium
set -a; source .env; set +a
```

| Setting | Notes |
|---|---|
| Model | `gemini-3.8-flash`, called through `generateContent`. Confirm the ID and price on Google's model and pricing pages before a recorded run; the introductory Flash price ends 2026-12-31 |
| Thinking level | `low`, `medium` or `high` (`minimal` is not supported). Set by the bake-off below |
| Temperature | Not sent. Google's guidance for Gemini 3.x is to leave it at the default |
| Output ceiling | `PFIA_GEMINI_MAX_OUTPUT_TOKENS=32768`; thinking tokens count against it, and a truncated answer is refused, not parsed |
| Retries | `PFIA_HTTP_RETRIES=4` on 429 and 5xx, honouring Retry-After |
| Extra settings | `PFIA_GEMINI_EXTRA_BODY` (JSON) is merged deeply into each request body |
| Data terms | Use the paid tier. Policies are generally public records, but set retention terms anyway |

## 2. Smoke test

```bash
PYTHONPATH=src python3 -m pfia adapter-check --adapter gemini --model gemini-3.8-flash --show-prompt
PYTHONPATH=src python3 -m pfia review --profile data/profiles/city.json \
    --policy tests/fixtures/policy_deficient.txt --schedule-b-v2
```

The first sends one control against a probe passage; expect `Response shape parsed and at
least one quote verified against the document.` The second runs the synthetic deficient
policy end to end on Gemini (it uses `PFIA_ADAPTER`/`PFIA_MODEL`); the `SCHEDULE B v2` block at
the end should name conflicts such as `BCD-04, BCD-05` on brokered CDs.

If either fails, the message names the cause, for example `model adapter error: GEMINI_API_KEY
is not set` or `gemini HTTP 429 ...: RESOURCE_EXHAUSTED: ...`. Fix that before going further.

## 3. Ground truth

```bash
PYTHONPATH=src python3 scripts/bakeoff.py --config bakeoff.gemini-flash.example.json --template
```

writes `benchmark/ground_truth/<case>.template.json` for the seven golden cases, prefilled
from the offline stand-in. For each file a reviewer:

1. corrects `instruments`: for every authorized instrument, the condition IDs that truly
   conflict with the statute (empty list if none);
2. corrects `controls`: the true status of each Core Schedule A control (`ALIGNED`,
   `PARTIALLY_ADDRESSED`, `NOT_ADDRESSED`, `CONFLICTS`);
3. fills `reviewed_by` and `reviewed_on`, sets `"reviewed": true`, and saves the file without
   `.template`.

Only reviewed files are scored. To add previously reviewed client policies, list them in
`benchmark/cases.json` (`{"cases": [{"id", "policy", "profile", "facts", "ground_truth"}]}`),
keep the policies under `benchmark/policies/` (git-ignored), and set `"benchmark":
"benchmark/cases.json"` in the config.

## 4. Choose the thinking level (bake-off)

```bash
cp bakeoff.gemini-flash.example.json bakeoff.json
PYTHONPATH=src python3 scripts/bakeoff.py --config bakeoff.json
```

Three candidates, each `gemini-3.8-flash` at `low`, `medium` and `high`, three repeats per
case. Output: `bakeoff-results/<timestamp>/report.md` and `results.json` (metrics and model IDs
only, no policy text).

| Metric | Meaning | Threshold |
|---|---|---|
| `false_conflicts` (+ `a_false_conflicts`) | A conflict the reviewer did not find: the costliest error | Fewest wins |
| `missed_conflicts` (+ `a_missed_conflicts`) | A reviewer conflict read as anything but conflict or UNKNOWN | Tie-break |
| `sent_to_review` | A reviewer conflict read as UNKNOWN: safe, costs reviewer time | Reported |
| `unknown_rate` | UNKNOWN share of active conditions | ≤ 0.15 |
| `quote_verified` | Affirmative claims whose quote was found | ≥ 0.98 |
| `stable` | Instruments with identical facts across repeats | Reported |
| `failures` | Adapter errors, including unusable JSON | 0 |
| `cost_per_policy`, `seconds_per_policy` | From Gemini's token counts and the configured price | Final tie-break |

The selection rule is fixed in the script: within the thresholds, fewest false conflicts,
then fewest missed conflicts, then lowest cost. If no candidate qualifies, `selected` is
empty; send the report rather than loosening a threshold.

Set the winning level in `.env` (`PFIA_GEMINI_THINKING_LEVEL=...`).

## 5. Record the run

```bash
PYTHONPATH=src python3 scripts/bakeoff.py --config bakeoff.json --record engagements/recorded-run
```

Keep only the selected candidate in `bakeoff.json` before recording. Each case directory gets
`cassette.json` (Schedule A Core) and `cassette-b2.json` (Schedule B v2). Each cassette's
`_run` names the candidate, case, served model ID and time; `_meta` records, per call, the
requested and served model, token counts and the prompt's SHA-256. No key is ever written.

Replay, with no network and no tokens:

```bash
PYTHONPATH=src python3 -m pfia review --profile data/profiles/city.json \
    --policy tests/fixtures/policy_deficient.txt --schedule-b-v2 \
    --adapter replay --cassette engagements/recorded-run/<candidate>/<case>/cassette-b2.json
```

The recorded run is the input to adopting Schedule B v2 and retiring the 0.18.0 instrument
schedule: `scripts/compare_schedule_b.py` is re-run against it and every status difference
is explained before adoption.

## 6. Use on an engagement

```bash
pfia extract --profile engagements/<client>/profile.json --policy engagements/<client>/policy.pdf \
    --cache engagements/<client>/cache --out engagements/<client>/extraction.json
pfia review --profile engagements/<client>/profile.json --policy engagements/<client>/policy.pdf \
    --extraction engagements/<client>/extraction.json --schedule-b-v2 \
    --out engagements/<client>/ledger.json
pfia report --ledger engagements/<client>/ledger.json --entity "..." --out engagements/<client>/report.pdf
pfia purge engagements/<client>/cache --yes
```

## Not used in this configuration

- **Claude adapters.** The code remains (`--adapter anthropic`), but the Claude path is not
  part of this runbook until calls are working again; `bakeoff.example.json` still lists Claude
  candidates, and the bake-off skips any candidate whose key is missing.
- **Two-reader mode** (`--second-adapter`). It needs a second, independent provider: two
  readings from the same model share the same errors. It returns when a second provider is
  available (ADR 0012).
