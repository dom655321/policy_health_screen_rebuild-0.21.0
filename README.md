# tx-pfia-register

A machine-executable control register for reviewing a Texas public entity's investment
policy against the Public Funds Investment Act (Tex. Gov't Code ch. 2256, Subchapter A),
with a deterministic evaluator and a content-addressed finding ledger. Built for a firm that
manages short-term fixed income for public entities, so the review concentrates on
**authorized investments and the investment management provisions**.

**Release 0.21.0.** 89 controls in two schedules plus the proposed Schedule B v2 condition
catalogue (29 instruments, 80 active conditions); categorical statuses with no numeric
scoring (ADR 0010); Core/Context tiering (ADR 0011); Gemini 3.8 Flash as the reader
(ADR 0012); redline and mandate fit (ADR 0013); 384 tests, 7 golden cases, a reproducible statute snapshot, zero runtime
dependencies in the core. GTOT certification analysis is paused.

## Start here

| You want to | Read |
|---|---|
| Install, run the tests, review a first policy | `docs/SETUP.md` |
| Configure Gemini, choose the thinking level, record the run | `docs/MODEL-RUNBOOK.md` |
| Benchmark against the team's past reviews | `docs/RUNBOOK.md` |
| Understand how a result is reached (non-technical) | `docs/METHODOLOGY.md` |
| Review the register or the model's results | `docs/REVIEW-GUIDE.md` |
| Produce the redline or mandate fit | `docs/OUTPUTS.md` |
| Know what was decided and why | `docs/adr/` (0009-0012 for this release) |
| See what is deferred or open | `docs/DEFERRED.md`, `docs/BACKLOG.md` |
| Find something in the tree | `docs/LAYOUT.md` |

## Design in one paragraph

A policy review is a text-to-norm mapping problem, not a portfolio audit. Only some PFIA
obligations live in the policy document; the rest bind conduct, and their absence from a
policy is not a defect. Every control therefore carries an evidence locus, an applicability
predicate and a band; the evaluator gates on all three before reviewing anything. The
language model is reduced to a reader that returns facts with verbatim quotes, every quote is
verified against the document, and every comparison with the statute is made in code, so
results are reproducible and a failure to read reads UNKNOWN rather than passing.

## What is reviewed

| Section of the report | Register | Depth |
|---|---|---|
| Authorized investments | `instrument-schedule` (53 controls) sets the status; `instrument-conditions` (Schedule B v2, proposed) runs alongside with `--schedule-b-v2` | Full |
| Investment management provisions | `policy-content`, 19 Core controls | Full, element by element |
| Policy governance (summary) | `policy-content`, 17 Context controls | One line each: addressed or not expressly addressed |

Section status comes from fixed rules, first match wins: **Review in progress** (applicability
unresolved), **Revisions recommended** (a stated term differs from the Act), **Additions
recommended** (a required provision not expressly addressed), otherwise **Addresses the
provisions reviewed**. Advisory items and the governance summary never set a status.

## Quick start

```bash
make test             # 384 tests
make golden           # 7 golden cases
make verify           # every control's statute text against the snapshot
make statute-rebuild  # snapshot reproduces from the pinned raw HTML
make review           # synthetic policy, offline, writes build/ledger.json
make coverage-map     # sections of the subchapter that carry controls
make audit            # authoring report
make schema           # every register against its schema (pip install jsonschema)
make export-review    # reviewer CSV and workbook
make bless            # regenerate golden expectations after an intended change
```

With the model (`.env`: `GEMINI_API_KEY`, `PFIA_ADAPTER=gemini`, `PFIA_MODEL=gemini-3.8-flash`):

```bash
set -a; source .env; set +a
PYTHONPATH=src python3 -m pfia adapter-check --adapter gemini --model gemini-3.8-flash

PYTHONPATH=src python3 -m pfia extract \
  --profile data/profiles/city.json --facts tests/fixtures/facts_deposit_program.json \
  --policy tests/fixtures/policy_deficient.txt \
  --cache .cache/extraction --out build/city_extraction.json

PYTHONPATH=src python3 -m pfia review \
  --profile data/profiles/city.json --facts tests/fixtures/facts_deposit_program.json \
  --policy tests/fixtures/policy_deficient.txt \
  --extraction build/city_extraction.json --schedule-b-v2 --out build/ledger_city.json

PYTHONPATH=src python3 -m pfia report --ledger build/ledger_city.json --entity "Example City" --out build/report.pdf
```

Core controls go to Gemini; Context controls are answered offline and never reach the model.

## The ledger is the deliverable

The report is a projection of the ledger. The ledger records the register versions and their
`law_in_force_as_of` dates, the document's SHA-256, the reader used, the entity profile,
every finding with its status, section, band, spans and reasons, the section statuses, and a
SHA-256 over the whole body. Nothing may appear in a client report that is not in the ledger.

## Golden cases

Each case in `tests/golden/` pins the whole pipeline for one policy against one entity
profile: extraction counts, every control's status, verdict, band and section, and every
section status. When a case moves, `make golden` names each control that changed.

| Case | Pins |
|---|---|
| `water-authority-conforming` | Water Code ch. 36/49 training exemptions, advisory-band separation |
| `water-authority-pdf` | Ingestion neutrality: the same policy as a PDF gives the same statuses |
| `city-deficient-deposits` | Anti-pattern library, brokered deposit / brokered CD split |
| `city-detected-instruments` | No facts file: the authorized set is read from the document and stays open under blanket incorporation |
| `isd-corporate-bonds` | Fact-test path, class-gated Sec. 2256.0204 |
| `tollway-enumerated-list`, `tollway-unindented` | One authorizing sentence followed by an enumerated list, and the same list without indentation |

## Authoring a control

1. Pin the citation to the smallest unit carrying one testable proposition.
2. Paste `source_text` verbatim from the snapshot; the law-sync gate checks it.
3. Set `policy_text_expectation` (the band) on the control, and on any element whose band
   differs. Ask where the duty lives, not how important it feels.
4. Set `relevance`: `CORE` for investment provisions, `CONTEXT` for governance.
5. Decompose into `required_elements` written as "The policy requires ...", one condition each.
6. Write `anti_patterns` from real defects; give generic phrases `anti_pattern_anchors`.
7. Reference shared predicates rather than inlining logic.

Schedule B v2 conditions also need a verbatim `quote` that appears in a section the condition
cites; the loader fails otherwise.

## Known limits

- Not yet validated against the team's past reviews (`docs/RUNBOOK.md`).
- Schedule B v2 is proposed until a recorded Gemini run explains every difference from the
  0.18.0 instrument schedule.
- One reader: two-reader mode needs a second, independent provider.
- Ch. 2257 is outside the register; deposit collateral is requested as evidence.
- GTOT is paused; eight instruments are outside the client base and report as not reviewed
  (special-purpose authorities, ISD corporate bonds, and the higher-education funds and corporate debt).
