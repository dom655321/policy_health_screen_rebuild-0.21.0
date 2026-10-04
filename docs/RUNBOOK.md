# Benchmark runbook: prior reviews

Measuring the pipeline against policies the team has already reviewed, on Gemini 3.8 Flash.
This is Step 4 of the build sequence and comes after the model runbook
(`docs/MODEL-RUNBOOK.md`) has chosen a thinking level and `adapter-check` passes.

Two harnesses, two questions:

| Harness | Question | Ground truth |
|---|---|---|
| `scripts/bakeoff.py` | Which model configuration reads best? | `benchmark/ground_truth/*.json` (instrument conflicts by condition ID; Core control statuses) |
| `scripts/benchmark.py` (this runbook) | Where does the register disagree with the team's past reviews, and why? | `engagements/ground-truth/*.json` from `data/ground-truth/TEMPLATE.json` (reviewer verdict per control, plus `unmapped_findings`) |

## 1. Verify offline

```bash
make test && make golden && make verify
```

## 2. One entity profile per policy

```bash
pfia profile init --entity "Example Regional Water Authority" --out engagements/example/profile.json
# answer all 18 questions, then:
pfia profile check --profile engagements/example/profile.json
```

`profile check` exits non-zero until every question is answered. Do not benchmark against an
incomplete profile: unresolved controls are left out of the comparison, so an incomplete
profile silently shrinks the measurement.

## 3. Confirm ingestion and instrument detection

```bash
pfia ingest --policy engagements/example/policy.pdf
pfia instruments --policy engagements/example/policy.pdf
```

Extraction quality is `OK`; the authorization state is `enumerated`; the detected list matches
what a reader would say the policy authorizes. A missing type is a lexicon gap, and adding
terms to `data/registers/instrument_lexicon.json` is cheaper than any other fix.

## 4. Transcribe the prior reviews

One file per policy in `engagements/ground-truth/`, copied from `data/ground-truth/TEMPLATE.json`.

- **Core controls only.** Context controls are summarized as addressed or not expressly
  addressed (ADR 0011); a reviewer verdict on one of them is not compared like for like.
  The tier of every control is in `data/registers/policy-content/register.json` (`relevance`)
  and in the approved tiering workbook (TIER-2026-09-27).
- **Only what the prior review actually addressed.** A guessed CONFORMING is
  indistinguishable from a real one and quietly inflates agreement.
- **`unmapped_findings`** holds anything the reviewer raised that no control could have
  produced. It measures register depth, which nothing automated can.

## 5. Run and record

```bash
python3 scripts/benchmark.py --truth engagements/ground-truth \
    --adapter gemini --model gemini-3.8-flash --record --out build/benchmark
```

With `PFIA_ADAPTER`/`PFIA_MODEL` set in `.env`, `--adapter` and `--model` can be omitted.
`--record` writes a cassette per case, so the run replays exactly during review without
re-spending tokens or re-sending client text:

```bash
python3 scripts/benchmark.py --truth engagements/ground-truth --adapter replay --out build/benchmark
```

## 6. Adjudicate

`build/benchmark/adjudication.md` lists every disagreement with the evidence the pipeline
relied on. Resolve each as one of three things, because they have different fixes:

| Resolution | Fix |
|---|---|
| Control wrong | Edit the register; re-bless the golden cases (`make bless`); the diff is the point |
| Reviewer wrong | Correct the ground truth and note why, so the case stays usable |
| Evidence missed | Register right, reading failed. A discarded quote is a model problem; no candidate window is a search-directive problem |

Read `unmapped_findings` first: register gaps outrank status disagreements.

## 7. Purge

```bash
pfia purge build/benchmark/cache engagements/example/cache --yes
```

Ledgers and rendered reports are the artifacts meant to survive. Caches, cassettes and
derived text hold verbatim policy text and should not outlive the engagement.
