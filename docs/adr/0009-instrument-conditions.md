# ADR 0009 - Authorized investments as typed, atomic conditions (Schedule B v2)

**Status:** Proposed · **Date:** 2026-09-27 · **Supersedes in part:** ADR 0006 (pair structure), ADR 0008 (anti-patterns for Schedule B)

## Context

The 0.18.0 instrument schedule holds 53 controls: a conformity/completeness pair per
instrument. The element audit found the structure, not the drafting, was the limit:

- Each conformity control carries one aggregate element ("states no term that conflicts"),
  so a DEFICIENT verdict cannot say which term conflicts.
- Only 11 numeric limits are typed. Rating floors, permitted sets and custody terms are
  judged by the model or by document-wide literal anti-patterns, several of which match
  conforming or stricter text ("AA-" inside "AAA-m"; the Sec. 2256.010(a) CD conditions
  tripping the negotiable-CD controls).
- 20 compound completeness elements hide partial restatement; 4 split a statutory
  either/or into two half-weight elements.
- The firm's use is adherence: every component of every authorized investment, compared
  term by term. That needs typed comparisons, not text similarity.

## Decision

1. **One condition per requirement.** 29 instruments, 129 conditions, each a requirement a
   policy can state, contradict or omit on its own. Statutory alternatives stay inside one
   condition (`ANY_OF`).
2. **Typed tests.** `CAP`, `FLOOR`, `RATING_FLOOR` (ordinal cross-agency scales, notch or
   category granularity, agency count, at-purchase or continuous basis), `SUBSET`,
   `REQUIRED`, `PROHIBITED`, `ANY_OF`.
3. **Division of labour.** The model extracts facts (value, unit, stated, contradicted,
   span). Code decides stricter, equal or looser. A replayed extraction always yields the
   same verdict.
4. **Six states.** CONFORMING, STRICTER, BY_REFERENCE, SILENT, CONTRADICTED, UNKNOWN.
   Conformity (statutory band) fails only on CONTRADICTED and names every contradicted
   condition. Completeness (advisory band) is the weighted share satisfied. Silence is
   never a conformity finding (Sec. 2256.024). A missing fact is UNKNOWN, never SILENT
   (ADR 0005). Approximate unit conversions within three days of a limit are UNKNOWN.
5. **Evidence gate.** Every condition carries a verbatim `quote`; the loader fails if any
   quote is absent from the committed statute snapshot.
6. **Effective limits.** Each trade-testable condition emits the binding term (policy ∧
   statute) with its source, for use as a client constraint set.
7. **`binds`.** Each condition names who carries the duty: entity, pool, fund, counterparty,
   security, or the investment manager (Sec. 2256.011(g); Sec. 2256.0204(f)).
8. **Anti-patterns retired as scoring inputs** for this schedule. Contradiction is an
   extracted fact confined to the instrument's clause.
9. **Conduct goes to the evidence request list** (`data/registers/evidence-requests/`),
   never to an index.

## Verified against the statute snapshot (2026-09-27)

| Item | Result |
|---|---|
| All 89 0.18.0 control `source_text` | In force as written (`make verify` passes) |
| State of Israel bonds, Sec. 2256.009(a)(6) | Present in statute; no code in 0.18.0 → added (`ISRAEL_BONDS`) |
| Reciprocal-deposit condition, Sec. 2256.010(b) | **Absent** from current text; 2017 checklist superseded; not added |
| Pool: Act-approved investments, daily mark-to-market, $1.00 NAV band, advisory board | Present in Sec. 2256.016(a), (f), (g) → added (POL-02, POL-06–POL-09) |
| Repo collateral value at disbursement, Sec. 2256.011(b)(2) | Present; untested in 0.18.0 → added (REP-04) |
| Joint-account duties on the investment management firm, Sec. 2256.011(g) | Present; untested in 0.18.0 → added (REP-09–REP-11) |

## Consequences

- `status: proposed`. The 0.18.0 schedule continues to score until adoption.
- Lexicon: US_OBLIGATIONS splits into four codes; ISRAEL_BONDS, MINERAL_RIGHTS_MUNI/JUCO and
  DECOMMISSIONING_TRUST are new or renamed. `instruments.py` detection must map them.
- Extraction adapter: one fact per condition in place of per-element span judgments.
- Golden cases: re-bless after wiring; the diff shows every instrument verdict that moves.

## Would overturn this decision

Ground-truth adjudication showing typed facts cannot be extracted reliably from real
policies (UNKNOWN rate above an agreed threshold), or counsel reading "A or its
equivalent" as a category (change MUN-02 and SLN-05 granularity; no structural change).

## Addendum (2026-09-27): wiring, parallel run

- `pfia.conditions.wiring` detects instruments with a merged lexicon
  (`instrument-conditions/lexicon_supplement.json` on top of the base file, which is not
  modified), maps codes (aliases, entity-class splits, class gates), builds one prompt per
  instrument, verifies every affirmative fact against the document and evaluates.
- A fact that asserts anything without a quote found in the document is discarded; its
  condition reads UNKNOWN. A missing answer is UNKNOWN, never silence.
- `pfia.conditions.standin.ConditionStandIn` is the offline stand-in. It reads figures,
  ratings, agency counts and basis by pattern, REQUIRED by keyword overlap, and ANY_OF and
  contradictions only from catalogue cues (`cues`, `outside_cues`, `contradiction_cues`).
  It does not map SUBSET vocabularies. Not review-grade.
- `pfia review --schedule-b-v2` records the run as `instrument_conditions` in the ledger with
  `section_status_if_adopted`. It never changes a section status; goldens are unaffected.
- `scripts/compare_schedule_b.py` writes `docs/audit/schedule-b-parallel-run.md`. First run
  (stand-in): 67 instrument rows across 7 cases; v2 confirmed 12 of the 14 0.18.0 conflicts,
  added none, and left the other two REVIEW_REQUIRED (pool rating tested at purchase with no
  rating stated; ISD corporate bond terms unread). Nothing 0.18.0 flagged reads ALIGNED in v2.
- **Retirement gate for 0.18.0 Schedule B:** a recorded model run (cassette) over the golden
  and benchmark policies, with every status difference in the parallel-run report explained.
