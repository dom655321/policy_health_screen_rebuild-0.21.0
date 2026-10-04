# ADR 0006 - Conformity and completeness in the instrument schedule

Status: accepted (2026-09-13). **Superseded in part by ADR 0009** (one typed condition per requirement in Schedule B v2) **and ADR 0010** (no weighted completeness). The conformity/completeness distinction itself still holds. Kept as the record of the original decision.

## Context

The first real policy run produced 24 non-conforming statutory controls, and half of them
were Schedule B controls failing for the same reason: the policy named an instrument
without restating that instrument's statutory conditions.

The clearest case. A tollway authority policy authorized:

> Banker's acceptances with a stated maturity of 180 days or less and whose endorsing banks
> are constantly monitored as to financial solvency by the Investment Officers.

The control scored 1 of 4 - no liquidation-at-maturity clause, no Federal Reserve collateral
eligibility, no acceptor rating. But Sec. 2256.012 conditions the *investment*, not the
policy text: a bankers' acceptance failing those tests is not an authorized investment
whether or not the policy mentions them. Sec. 2256.005(b)(4)(A) requires "a list of the
types of authorized investments" - not a restatement of each type's conditions - and
Sec. 2256.024 makes the conditions bind of their own force.

That policy had violated nothing. Its 180-day limit is stricter than the statutory 270, and
Sec. 2256.024 makes restriction conforming. The register was demanding recitation the
statute does not require, and the register was wrong.

## Decision

Every instrument carries two controls.

**Conformity** is statutory. It tests that nothing the policy states about the instrument
conflicts with the statute. Its elements are tested by absence: a negative element carrying
the control's anti-pattern library, plus one conditional element per figure the statute caps.
A conditional element is satisfied when the policy states no figure, and evaluated against
the statutory limit when it states one. Silence is not a deficiency; 365 days where the
statute says 270 is, and stays CRITICAL.

**Completeness** is advisory. It carries the original affirmative elements - the statutory
conditions restated in the policy - at ADVISORY severity. Restating conditions is good
drafting and what GTOT looks for, but a miss is an enhancement, never a statutory failure.

Two options were rejected. Moving Schedule B wholesale to the advisory band would have lost
the ability to flag a policy authorizing on wrong terms, which is the genuinely dangerous
case. Per-element bands would have avoided the cardinality growth but made the band harder
to explain to a board, and the band is the thing a board reads.

## Consequences

- Schedule B grows from 27 controls to 53. Cardinality is the cost; the report gains a
  sentence a reviewer can sign: this policy authorizes commercial paper on terms consistent
  with Sec. 2256.013, and does not restate the conditions, which is not required.
- The statutory index rises and the advisory index becomes informative rather than
  near-empty. On the tollway fixture: 35 statutory controls scored, 20 advisory.
- Conditional elements needed a third answer from the fact tests. A referenced-but-unstated
  figure resolves to UNKNOWN rather than failing the comparison closed, which would have
  read as a policy stating a non-conforming figure rather than one stating none.
- Schedule A is untouched. Its controls rest on "the investment policies must include",
  which is a policy-content mandate on its face. The defect was specific to instruments.

## Revisit when

Ground truth shows reviewers treating an unrestated condition as a deficiency. That would
mean the profession reads Sec. 2256.005(b)(4)(A) more broadly than this ADR does, and the
bands should follow the profession rather than my reading of the section.
