# Changelog

One entry per release. Register versions move on their own cycle and are noted where they
changed, because a register change is a change to what the firm asserts about a client's
statutory position.

Entries marked **calibration** changed what counts as a finding. Each rests on an ADR that
names the condition which would overturn it.

## 0.21.0 - 2026-10-04 - Screen report rebuilt; reading-reliability guards (ADR 0014)

- `pfia report` renders the rebuilt screen (`screen.html`): result and section tiles in the
  current order, scope statement, leading Core and instrument items, work queue, authorized
  investments condition by condition (Schedule B v2), Core cards with proposed language,
  governance summary, restatement items, evidence requests, provenance. "HSAM" branding and all
  audit vocabulary removed from every page. Earlier designs: `--template screen-0.19`, `legacy`.
- Stdlib PDF reader joins kerned fragments on the same line ("q uarter ly" -> "quarterly").
  Quality check counts word-splitting artifacts and degrades the document with a remedy.
  New `pdf` extra installs pypdf.
- Reliability guard shared by all outputs: degraded extraction or no enumerated authorized list
  is flagged on page one; mandate fit shows Cannot determine instead of Blocks.
- Mandate fit compares portfolio durations across days, months and years.
- Redline proposes conflicts resting on a verified literal match even when another element's
  quote was discarded.
- Register versions 2026.10.04; condition catalogue 0.2.0-proposed.
- Examples script also renders the screen.

## 0.20.1 - 2026-10-02 - Approved Schedule B v2 review; mandate-fit layout

- **Approved re-review TR-2026-10-02** applied to the condition catalogue (all 129 conditions;
  supersedes TR-2026-09-27 and its follow-up): KEEP 79, REWORD 1, DROP 34, NOT_TESTABLE 15;
  80 active, 49 retired. ISD corporate bonds and both higher-education instruments join the
  five special-purpose authorities as not reviewed. SLN-06 reworded. NOT_TESTABLE conditions
  routed to evidence requests PBC-11, 13, 17, 19, 26. Repo and securities-lending custody remain
  congruent. Changes against the follow-up decisions are tabled in
  `docs/audit/team-review-2026-09-27.md`.
- Mandate fit layout: the example marker removed; "Internal · onboarding" placed under the
  report name; "For the onboarding conversation" renamed **Investment Policy Summary** and
  followed directly by the portfolio-level parameters on page one; "Instrument by instrument"
  renamed **Authorized Investment Review** and moved to page two.
- Example strategy: brokered-CD counterparty term removed (BCD-01 is now not testable).
- Parallel run regenerated: v2 confirms 12 of the 14 0.18.0 conflicts, adds none, aligns
  nothing 0.18.0 flagged; ISD corporate bonds now read not reviewed.

## 0.20.0 - 2026-10-01 - Redline and mandate fit from the ledger (ADR 0013)

- `pfia redline`: proposed amendments for Core provisions and authorized-investment terms,
  optional restatements, a hold list for readings to verify, and a draft resolution under
  Sec. 2256.005(e). `--statutory-only` leaves out optional restatements.
- `pfia mandate-fit`: internal onboarding view comparing a strategy file with the policy's
  binding terms, instrument by instrument, plus reviewer-entered portfolio limits.
  Examples in `data/mandates/`.
- `scripts/make_output_examples.py` writes example documents from the synthetic policies.
- Templates `redline.html`, `mandate_fit.html`, shared `outputs.css`; view data in
  `pfia.report.outputs`. `docs/OUTPUTS.md`.
- `proposed_text` (statute-derived policy language) on all 19 Core Schedule A controls.
- Draft language corrected where it still asked for more than the statute: Secs.
  2256.005(b)(4)(B), (D), (F), 2256.005(i), 2256.007(d).
- Schedule B v2 ledger block now carries each condition's binding term, requirement and
  verified quote.
- **Extraction provenance:** `pfia extract` records the reader in `_extraction`; `pfia review
  --extraction` uses it. A payload without it is treated as not review-grade, so its findings
  are queued for verification.

## 0.19.3 - 2026-09-30 - Entity profile answers validated

- `profile check` and every command that loads a profile now validate answers against their
  declared type. `classes` given as a string, or containing a non-ID, used to fail with
  `unknown entity class in profile: y` (a string was split into characters); it now names the
  problem, suggests the closest class ID, and lists the valid IDs. Yes/no answers must be
  true or false; quoted `"yes"`/`"no"`/`"y"`/`"n"` are accepted and reported, anything else is
  refused (a quoted `"no"` was previously truthy). Amounts accept `"$250,000,000"` and similar.
- Profile and register errors print one line and exit 2 instead of a traceback.
- `profile init` writes `_how_to_answer` into the questionnaire; SETUP step 7 explains each field.

## 0.19.2 - 2026-09-30 - Documentation for the Gemini configuration

- `docs/` rewritten for the current model: SETUP, MODEL-RUNBOOK (Gemini 3.8 Flash; thinking-level
  bake-off; recorded run), RUNBOOK (benchmark on Gemini, Core controls only), METHODOLOGY (no
  score; section rules; Core/Context; typed authorized-investment conditions), REVIEW-GUIDE
  (completed and open team reviews), DEFERRED (resolved, paused and new items), BACKLOG, LAYOUT.
  README replaced with a current entry document. ADRs 0004, 0006 and 0008 marked superseded in part.
- Removed from the docs: Claude-first commands, numeric indices and expected scores, the alignment
  score and score cap, weight redistribution, Schedule C mock-up instructions, the HSAM
  best-practice band, and the manual snapshot step.
- Fixes found while checking every documented command: `--out` creates its directory (`make
  review` failed on a fresh checkout); adapter errors print one line and exit 2 instead of a
  traceback; `scripts/benchmark.py` no longer defaults to retired model IDs (uses `--model` or
  `PFIA_MODEL`); `.gitignore` covers bake-off cassette names; Gemini bake-off candidate IDs are
  directory-safe (`flash-low`, `flash-medium`, `flash-high`).
- Ground-truth templates regenerated against the current register and tiering.

## 0.19.1 - 2026-09-30 - Gemini 3.8 Flash as the working reader

- Gemini 3.x requests follow Google's migration guidance: no temperature, reasoning effort via
  `PFIA_GEMINI_THINKING_LEVEL` (`thinkingConfig.thinkingLevel`: low, medium, high), and a 32k
  output ceiling (`PFIA_GEMINI_MAX_OUTPUT_TOKENS`) because thinking tokens count against it.
  Older Gemini models keep temperature 0.
- Gemini responses: thought parts are never parsed; blocked prompts and safety stops raise a
  named error instead of "no candidate text".
- Both providers: retries with backoff on 429 and 5xx (Retry-After honoured, `PFIA_HTTP_RETRIES`);
  HTTP errors now carry the provider's own message (e.g. `not_found_error: model ... not found`);
  `PFIA_*_EXTRA_BODY` merges deeply instead of replacing nested objects.
- `PFIA_ADAPTER` / `PFIA_MODEL` set the reader when `--adapter` / `--model` are not given;
  `.env.example` defaults to gemini / gemini-3.8-flash.
- Bake-off skips candidates whose API key is missing and accepts per-candidate `env`;
  `bakeoff.gemini-flash.example.json` compares low, medium and high thinking.

## 0.19.0 - 2026-09-29

Investment-provision focus: typed authorized-investment conditions (Schedule B v2, proposed),
categorical statuses in place of scoring, Core/Context tiers, GTOT paused, live model
providers with two-reader mode and a bake-off harness. ADRs 0009 to 0012.

### Schedule B v2 (proposed) **calibration pending adoption**
- Statute snapshot committed (`data/sources/GV.2256.txt`, retrieved 2026-09-27 from the
  Legislature's file server, `tcss.legis.texas.gov/resources/GV/htm/GV.2256.htm`). All 89
  control source texts verify. CI law-sync gate now blocking.
- `data/registers/instrument-conditions/`: 29 instruments, 129 typed atomic conditions,
  every quote verified against the snapshot. `status: proposed`; scores nothing yet.
- `pfia.conditions`: stdlib-only loader, ordinal rating scales, deterministic evaluator,
  instrument roll-up and effective-limit export. 32 tests.
- `data/registers/evidence-requests/`: 24 prepared-by-client requests covering every
  observational and extrinsic element; never scored.
- ADR 0009.

### Step 0 (element audit, anti-pattern library, snapshot provenance)
- **Schedule A, provisional element audit (EA-2026-09-27).** 79 logged changes: 31 rewordings
  to policy-duty form, 29 splits, 6 drops, 3 whole-control rebands (2256.006-b, 2256.017,
  2256.026), 4 elements marked for reband once band is element-level (Step 1), 3 queries.
  Every changed element carries `audit` metadata; full log in
  `docs/audit/element-audit-2026-09-27.json`. Schedule A now has 101 elements (was 91).
  2256.005(h) rewording corrected against the statute text.
- **Anti-patterns.** 25 defective pattern instances removed, 1 added, each with a reason.
  Generic-qualifier controls (25) declare `test.anti_pattern_anchors`: a hit counts only when
  an anchor term is in the same or preceding sentence. Negative elements follow the same
  anchors. Retrieval-window scoping was tried and rejected (it lost true findings in
  policies that avoid the statutory wording).
- **Schedule B v2 fixes.** Percentage limits compare only on the same base (else UNKNOWN);
  quotes must appear inside a cited section; CD "rating of at least 1" labelled interpretive.
- **Statute provenance.** `scripts/fetch_statute.py` (`--rebuild`, `--check`, `--fetch`),
  pinned raw HTML, `data/sources/MANIFEST.json`, weekly `statute-drift` workflow. Snapshot
  date corrected to 2026-09-27.
- **Schemas.** `scripts/validate_schemas.py` validates each register against the schema its
  `$id` names; schemas added for instrument-conditions and evidence-requests.
- Heuristic adapter ignores the frame words "requires" and "addresses".
- Goldens re-blessed; `docs/audit/golden-diff-step0.md` records every flip and its cause.

### Step 1 (categorical status, ADR 0010)
- Numeric scoring removed end to end: weights (registers, schema, model, loader), per-control
  score, statutory and advisory indices, CRITICAL-only gate, score cap, health bands, and in
  Schedule B v2 the completeness fraction, `trade_testable` and `effective_limits()`.
- Item statuses (ALIGNED, ALIGNED_BY_REFERENCE, PARTIALLY_ADDRESSED, NOT_ADDRESSED, CONFLICTS,
  REVIEW_REQUIRED, NOT_APPLICABLE) and section statuses by fixed rules; ledger `sections`
  replaces `scores`.
- Element-level band; 2256.005-f e2/e4 and 2256.006-a e1/e2 moved to the advisory band.
- Findings routed by register authority to PFIA requirements, authorized investments or GTOT.
- Loader: missing `policy_text_expectation` is an error; cross references are validated.
- Evaluator negative elements honour `anti_pattern_anchors` (matches the runner).
- Registers' `law_in_force_as_of` set to 2026-09-27, the verified snapshot date.
- Goldens re-blessed on statuses; `docs/audit/golden-diff-step1.md`: one verdict moved
  (2256.006-a, ISD case, element-level band), every other verdict and band unchanged.
- HSAM best-practice framing removed from the report layer; the advisory section is
  "Provisions commonly restated".

### Step 2 (Schedule B v2 wired, parallel run)
- `pfia.conditions.wiring`: detection with a merged lexicon (new codes TX_OBLIGATIONS,
  GUARANTEED_OBLIGATIONS, AGENCY_CMO, ISRAEL_BONDS; aliases and class splits), per-instrument
  prompt with a machine-readable request, quote verification per fact, deterministic
  evaluation, ledger block `instrument_conditions`. Base lexicon and 0.18.0 detection unchanged.
- `pfia.conditions.standin.ConditionStandIn`: offline stand-in extractor.
- Catalogue: extraction cues on 36 conditions (ANY_OF alternatives, outside and contradiction cues).
- `instruments.detect(..., lexicon=...)` accepts a supplied lexicon.
- CLI: `pfia review --schedule-b-v2`.
- `scripts/compare_schedule_b.py` and `docs/audit/schedule-b-parallel-run.md`.
- 8 wiring tests; goldens unchanged.

### Team review TR-2026-09-27 (Schedule B v2)
- Applied 129 verdicts: 74 kept, 46 dropped, 7 not testable (retired, kept for the trail), 2 without a verdict.
- Five instruments with no remaining conditions are `NOT_REVIEWED`: reported, never aligned, never set a status.
- Evidence requests: PBC-25 (secured CD collateral), PBC-26 (MMF prospectus); dropped references removed; PBC-24 removed.
- Parallel run regenerated; `docs/audit/team-review-2026-09-27.md` lists eight items to confirm.
- Follow-up TR-2026-09-27a: reinstated REP-03/04/07/08, SLN-07 to SLN-10, BA-02 to BA-04; GTD-01 kept; MF-01 dropped;
  custody tested identically for repo and securities lending (`custody_set`); rationale recorded for CMO-02, ICB-07/08,
  DCD-03/04/05 and the five out-of-scope instruments. 86 active conditions, 43 retired.

### Scope realignment (ADR 0011)
- `relevance` tier on every control (Schedule A: 21 Core, 15 Context, provisional); evaluator
  depth switch (`context_depth`, default SUMMARY); new POLICY_GOVERNANCE summary section.
- Section order: authorized investments, investment management provisions, governance summary.
- `paused` register status; GTOT paused; Context evidence requests paused.
- Tag `v0.19-full-scope` marks the last full-scope build.
- Goldens re-blessed: 0 Core moves, 15 Context moves per case (`docs/audit/golden-diff-realignment.md`).

### Step 3 (live providers, two readers, bake-off; ADR 0012)
- Anthropic and Gemini adapters accept the Schedule B v2 conditions contract; served model and
  tokens captured; `PFIA_*_EXTRA_BODY` request settings; injectable transport for tests.
- Cassettes record `_run` and `_meta` provenance (served models, prompt hashes, tokens).
- Two-reader mode for Schedule B v2 (`second_adapter`, CLI `--second-adapter/--second-model`).
- Context controls answered offline at SUMMARY depth; `context_calls` counted separately.
- Live adapters require an explicit `--model`.
- `scripts/bakeoff.py`, `bakeoff.example.json`, `.env.example`, `docs/MODEL-RUNBOOK.md`,
  ground-truth templates for the seven golden cases.
- Team tiering TIER-2026-09-27 adopted: 2256.005(c) and 2256.006(b) to Context (19 Core, 17 Context);
  2256.005(k) unmarked, kept Core provisionally. Goldens re-blessed: counts only, no status moved.
## 0.15.0 - report redesign
- New default template `hsam_screen.html` built to the supplied design concepts. Page one is
  built from a separate `client_safe` context block: no control identifiers, no unreviewed
  draft language, no confidence labels, no extraction internals, and one page by
  construction. Tests assert both the block and the rendered cover are free of internal
  artifacts.
- Internal sections marked on their own face, so a detached page one cannot be mistaken for
  the whole document.
- New report sections: reviewer work queue grouped by action, authorized-investment set with
  the incorporation clause, undetermined controls, sections not evaluated.
- Inherited template retained as `--template legacy`.
- `--distribution client-draft` swaps the internal-use chip for a pending-review mark.

## 0.14.0 - flagging engine (ADR 0008) **calibration**
- Numeric limits removed from anti-pattern libraries. A literal "270 days" cannot tell a
  stricter limit from a looser one, and Sec. 2256.024 makes a stricter policy conforming.
  Ten strings removed; a test fails the build if a numeric limit reappears.
- Tiering judged on the loosest tier. The model reports the most permissive figure.
- A stated figure inside the statutory limit is recorded as stricter than statute.
- A stated figure exceeding the limit is DEFICIENT, not ABSENT.
- Every finding carries a review action; the ledger carries a sorted work queue.
- Negative element resolution moved from the adapter runner into the evaluator, so a
  replayed or cached payload gives the same answer as a live run.

## 0.13.0 - incorporation by reference (ADR 0007) **calibration**
- `SATISFIED_BY_REFERENCE` resolves a completeness control to CONFORMING where the
  authorizing clause incorporates the statutory conditions. Scope tracked: a clause in the
  stem governs the list, a clause inside one item is recorded but not generalised.
- No Schedule A control carries the effect, enforced by test.

## 0.12.0 - conformity and completeness (ADR 0006) **calibration**
- Every instrument split into a statutory conformity control and an advisory completeness
  control. Schedule B 27 -> 53 controls.
- Conditional fact elements: satisfied when the policy states no figure, evaluated against
  the statutory limit when it states one.
- 44 search directives added across eleven controls that had reported no candidate passage.
- `context_directives` and cross-reference following widen retrieval without making absence
  unprovable.

## 0.11.x - detection correctness
- Enumerated-list stem inheritance: the dominant Texas drafting pattern authorizes once and
  lists instruments as bare noun phrases. Reach bounded by distance from the last item
  rather than by indentation, which had truncated a real twelve-item list to its first item.
- Scoped exclusions restrict rather than remove.
- `pfia version` reports package, register, lexicon and coverage versions; artifacts stamped.
- Stdlib PDF backend rewritten to walk the page tree. It had been counting content streams,
  which doubled the page count and put the wrong page against every citation.

## 0.10.0 - vacuous-truth elements **calibration**
- Negative elements: satisfied by the absence of contradicting language. Demanding an
  affirmative quote for "any carve-out is limited to pool and mutual funds" failed the
  best-drafted policies.

## 0.9.x - the three unknowns (ADR 0005)
- Three-valued predicate logic and APPLICABILITY_UNRESOLVED.
- Entity profile questions derived from the register; reconciled in both directions.
- Authorized-investment set read out of the policy rather than supplied.
- Statutory coverage computed and entity-aware.
- Empty scoring pool returns None rather than 1.0.
- Ground-truth benchmark harness.

## 0.5.0 - 0.8.0
- PDF ingestion with pluggable backends, page mapping, quality gate (ADR 0003).
- Report rendering as an optional extra (ADR 0004).
- Register completed to full section coverage of Subchapter A: 63 controls.

## 0.1.0 - 0.4.0
- Normalized register, two schedules, deterministic evaluator (ADR 0001).
- Statutory and advisory bands.
- Model adapter layer with span verification and golden fixtures (ADR 0002).

