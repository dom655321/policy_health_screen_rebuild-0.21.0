# ADR 0011 - Scope realignment: investment provisions first, governance summarized, GTOT paused

**Status:** Accepted · **Date:** 2026-09-27

## Context

The firm manages short-term fixed income for Texas public entities. Team feedback: the
full review of provisions unrelated to that business (adoption, training, ethics filings,
compliance audits) reads as mission drift, adds failure points, and puts the firm's name on
conclusions it is not engaged to reach. The whole policy is still read.

## Decision

1. **Relevance tier per control.** `relevance: CORE | CONTEXT`. Schedule A: 21 Core, 15
   Context (provisional, `relevance_review.status: PROVISIONAL`, pending the team's marks in
   `schedule-a-core-context-tiering.xlsx`). Schedule B and Schedule B v2: Core throughout.
   Quarterly reporting (Sec. 2256.023(a)-(b)) is Core: the firm prepares the reports.
2. **Depth switch.** `review(..., context_depth="SUMMARY")` (default) reduces a Context
   finding to one line in a new POLICY_GOVERNANCE section: addressed or not expressly
   addressed. No element status, conflict or advisory split is reported, and the section is
   SUMMARIZED; it never sets a status. `context_depth="FULL"` restores the full-scope review.
   The full evaluation is kept in the finding's elements for the trail.
3. **Section order:** authorized investments, investment management provisions, policy
   governance (summary). The client screen carries the scope statement "Governance and
   administrative provisions are summarized, not reviewed in detail."
4. **Paused status.** A register marked `paused` is kept in the repository and loads only
   when named explicitly. GTOT is paused and absent from outputs (not "Not assessed").
5. **Evidence requests** deriving from Context provisions or out-of-scope instruments are
   `paused`, not deleted.
6. **Preservation:** tag `v0.19-full-scope` marks the last full-scope build; paused code
   stays under test.

## Consequences

- Golden cases: zero Core controls moved; 15 Context controls per case moved to the summary.
- Step 3 (live model): the runner should skip element extraction for Context controls at
  SUMMARY depth, which is where the cost and failure-point saving is realised.
- Presentation (Step 5): checklist rows, comments and redline language for Core only.

## Would overturn this decision

A client segment (for example full-mandate advisory) that engages the firm on governance;
set `context_depth="FULL"` or retier.

## Addendum (2026-09-27): team tiering adopted (TIER-2026-09-27)

Source: approved `schedule-a-core-context-tiering.xlsx` (SHA-256 on each control's
`relevance_review`). 35 of 36 controls marked; 33 as proposed. Changes: 2256.005(c) CD bid
methods and 2256.006(b) prudence adjudication moved to Context. The borderline 2256.005(e),
2256.005(f) and 2256.023(d) were confirmed Context. Result: 19 Core, 17 Context.
2256.005(k) (the firm's written acknowledgment) was left unmarked and stays Core as
PROVISIONAL pending confirmation. No section status moved in any golden case: both changed
controls were in the advisory band, so only the counts shifted to the governance summary.
