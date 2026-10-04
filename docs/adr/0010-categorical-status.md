# ADR 0010 - Categorical status in place of numeric scoring

**Status:** Accepted · **Date:** 2026-09-27 · **Supersedes:** the scoring parts of ADR 0004 and ADR 0006

## Context

The pipeline produced two weighted indices (statutory and advisory), a per-control score,
a CRITICAL-only mandatory-failure gate and a 0-100 health score capped at 59. The team asked
for outputs without numeric scoring. Three further problems made the change necessary rather
than cosmetic:

- Weights were authored, not derived; the index moved when an element was split even though
  the policy had not changed (element audit EA-2026-09-27).
- The CRITICAL-only gate hid HIGH-severity conflicts. The conforming fixture authorizes
  single-agency commercial paper without a letter of credit; it produced no mandatory failure.
- Band was set per control. Sec. 2256.005(f) carries one policy-content duty and three duties
  that bind by operation of law; a control-level band could not say so.

## Decision

1. **Item status** replaces score: ALIGNED, ALIGNED_BY_REFERENCE, PARTIALLY_ADDRESSED,
   NOT_ADDRESSED, CONFLICTS, REVIEW_REQUIRED, NOT_APPLICABLE. CONFLICTS (stated language the
   statute does not permit: a figure beyond a limit, an anti-pattern, a defeated negative
   element) is distinct from PARTIALLY_ADDRESSED, so nothing is inferred from a number.
   The register verdict (CONFORMING / DEFICIENT / ABSENT) is kept for continuity and is
   derived by the same rules as before; across all golden cases only one verdict moved, and
   only because of rule 3.
2. **Section status** by fixed rules, first match wins: REVIEW_IN_PROGRESS (any
   applicability unresolved) → REVISIONS_RECOMMENDED (any statutory-band CONFLICTS) →
   ADDITIONS_RECOMMENDED (any statutory-band NOT_ADDRESSED or PARTIALLY_ADDRESSED) →
   ADDRESSES_PROVISIONS_REVIEWED; NOT_ASSESSED when nothing is in scope. Advisory-band items
   never set a section status. Severity orders items; it never gates them.
3. **Element-level band.** An element may carry `policy_text_expectation`; the control is in
   the statutory band if any element is, and advisory elements are reported as
   `advisory_status`. Applied to 2256.005-f e2, e4 and 2256.006-a e1, e2.
4. **Routing by authority.** Findings route to PFIA_REQUIREMENTS, AUTHORIZED_INVESTMENTS or
   GTOT by register authority and schedule; the part within a section by band. The
   `authority` field, loaded since 0.16 and never read, now decides placement.
5. **Deleted, not deprecated:** control and element weights (data, schema, model, loader),
   `score`, `compliance_index`, `counts_toward_score` (now `in_scope`), `critical_failures`,
   the score cap, health bands, the advisory index, and in Schedule B v2 the completeness
   fraction, `trade_testable`, `weight` and `effective_limits()`.
6. **Counts are allowed.** Tallies of item statuses per section part describe; they are not
   a score. The client version may suppress them.
7. **Loader strictness.** A missing `policy_text_expectation` is a load error (it silently
   defaulted to REQUIRED); cross references into a loaded register must resolve.

## Consequences

- Ledger: `scores` is replaced by `sections`, `in_scope_controls`, `total_controls`,
  `unresolved_controls`; each finding carries `status`, `section`, `part`, `authority`,
  `advisory_status`. Golden cases pin statuses and section statuses.
- The internal and client templates render section statuses; the score grid and the
  Governance Maturity Index are gone from the logic (the template furniture is replaced in
  the presentation step).
- Negative elements now honour `anti_pattern_anchors` in the evaluator as well as in the
  runner; Step 0 applied anchors in the runner only, so a replayed payload could disagree.

## Would overturn this decision

A client or regulator requirement for a numeric measure. It would be computed in the
presentation layer from statuses, never stored in the register or the ledger.
