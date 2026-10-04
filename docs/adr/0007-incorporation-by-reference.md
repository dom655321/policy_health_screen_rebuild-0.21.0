# ADR 0007 - Incorporation by reference

Status: accepted (2026-09-14)
Supersedes part of ADR 0006

## Context

ADR 0006 split each instrument control into a statutory conformity control and an advisory
completeness control, on the reading that Sec. 2256.005(b)(4)(A) requires a list of
authorized types rather than a restatement of each type's statutory conditions. It flagged
the condition that would overturn it: reviewers treating an unrestated condition as a
deficiency.

Reviewers confirmed the reading, and went further. The authorizing clause in the policy that
prompted this reads:

> only the following investment types, **as further defined by the PFIA or such trust
> agreement**, are authorized for the investment of NTTA Funds

Their position: that clause defers to the specificity of the chapter and accepts current and
future limits on the investable universe. The drafting is widely adopted precisely because
it keeps the conditions current without a policy rewrite each time the legislature amends.

That is a stronger claim than ADR 0006 made. ADR 0006 said an unrestated condition is not a
deficiency. This says the conditions are **in the policy** - by reference rather than by
recitation - and an officer reading the policy is directed to them.

## Decision

Incorporation is a positive finding, not an exemption.

- Detection records an incorporation clause when it appears in an authorizing stem or an
  authorized-investment section. A recital does not count: the clause only means what it
  means where it governs the authorization.
- A new exemption effect, `SATISFIED_BY_REFERENCE`, resolves a control to CONFORMING with
  the clause as its reason and every element marked `incorporated by reference`. Recording
  it as NOT_APPLICABLE was rejected: that drops the control silently and loses the reason it
  passed, which is the opposite of what a working paper is for.
- All 26 completeness controls carry it. **No Schedule A control does**, and a test enforces
  that.
- Scope is tracked. A clause in the sentence introducing the list governs every item under
  it. The same words inside a single item govern that item alone, and are recorded with
  `applies: false` rather than generalised - passing conditions for instruments a clause
  never mentioned would be a worse error than the one this ADR fixes.

## Two limits worth stating

**Incorporation cannot supply what the entity must decide.** The maximum stated maturity
under Sec. 2256.005(b)(4)(B), the dollar-weighted average maturity under (C), the market
price monitoring method under (D) and the fund strategies under Sec. 2256.005(d) are entity
choices. No reference to the chapter answers them, which is why Schedule A is untouched.

**Incorporation does not cure a contradiction.** A clause saying the conditions apply cannot
make a stated 365-day bankers' acceptance limit conform to a 270-day statute. Conformity
controls are unaffected, and a stated term that conflicts stays a statutory failure at its
original severity.

## Distinguishing it from blanket incorporation

These look similar and mean opposite things.

| | Effect |
|---|---|
| "any investment authorized by the PFIA" | The set of **types** is open. A Sec. 2256.005(b)(4)(A) failure, and the authorized set is unresolved |
| "only the following types, as further defined by the PFIA" | The set of types is **closed**; each type's **conditions** float with the chapter. Conforming, and better drafting than recitation |

The register keeps them apart by source: blanket phrasing is read from the anti-pattern
library of TX-PFIA-2256.005-b-4-A-001, incorporation cues from their own lexicon list, and a
test asserts a blanket policy records no incorporation clause.

## Consequences

- On the tollway fixture the advisory index moved from 0.417 to 0.630, and the movement is
  entirely the completeness controls passing by reference. The statutory index is unchanged
  at 0.518, which is the point: the finding was never statutory.
- A policy with no incorporation clause still shows the advisory gap, so the register still
  distinguishes drafting that directs a reader to the conditions from drafting that leaves
  them to be found.

## Revisit when

An item-level incorporation clause appears in a policy where it matters. Mapping such a
clause to the single instrument it sits with is a contained piece of work, deliberately not
done here because over-generalising it is worse than not applying it.
