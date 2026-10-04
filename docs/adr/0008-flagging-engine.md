# ADR 0008 - The output is a work queue, not a verdict

Status: accepted (2026-09-15). **Superseded in part by ADR 0009** (anti-patterns retired as scoring inputs for Schedule B v2) **and the 2026-09-27 element audit** (generic anti-patterns anchored to their subject). Kept as the record of the original decision.

## Context

The register has been built as though its output were a conclusion. It is not. It is an
ingestion engine that flags candidates for human review, and its output is an internal
working paper that does not go to a client or a board.

That framing has been implicit and it changed decisions. Two things follow from stating it.

**Recall matters more than precision, but usability caps how far that goes.** A flag that
turns out fine costs a reviewer under a minute. A missed deficiency costs the firm's
credibility. So the register should err toward flagging - but 29 items of which 8 are real
trains reviewers to skim, and a skimmed list is worse than a short one. The resolution is
not to suppress findings but to say, per finding, which kind of check it needs.

**Edge cases are the normal case.** Reviewers pointed out that every policy carries its own
nuances, and the register cannot be built to anticipate them. What it can do is route each
finding to the right kind of human attention and be explicit about what it did not decide.

## Decision

**Every finding carries a review action.** Derived, not authored:

| Action | What it means |
|---|---|
| `VERIFY_EXTRACTION` | A quotation was discarded, or the extractor is not review-grade. Check the passage before treating this as a policy gap |
| `CONFIRM_ABSENCE` | Nothing matching the subject was found anywhere. Confirm the policy is silent rather than phrased in words the register does not search for |
| `READ_THE_PASSAGE` | Language known to defeat the requirement was located. Either a real defect or a phrase used differently |
| `INTERPRETIVE` | The controlling text is contested or the control rests on a reading. A judgment call, not a lookup |
| `REVIEW_FINDING` | Elements unsatisfied on located evidence. Ordinary review |

The ledger carries a `review_queue` sorted for work, and the action appears in the report's
analysis line. Sorting findings by the kind of attention they need is worth more than any
further refinement of the score.

**Numeric limits are never anti-patterns.** A reviewer's example settled this. A client
policy authorised commercial paper at A-1+ to 270 days and A-1 to 180 days - both tiers
inside the statutory 365. The register carried "270 days" as a commercial paper
anti-pattern, intended to catch the bankers' acceptance limit copied into the wrong clause,
and it would have flagged that policy as deficient for being stricter than the statute.

A literal figure cannot distinguish a stricter limit from a looser one, and Sec. 2256.024
makes a stricter policy conforming. Ten numeric strings were removed from the anti-pattern
libraries; the conditional fact tests compare numbers and are the correct mechanism. A test
now fails the build if a numeric limit reappears as an anti-pattern, with an allow-list for
the strings that carry a digit without being a limit - rating grades, section numbers, and
the signature of one section's authority copied into another.

**Tiering is judged on the loosest tier.** Tiering always narrows, so the most permissive
figure the policy allows is the one that has to clear the statute. The model is instructed
to report that figure. Where the stated figure is strictly inside the statutory limit, the
finding records that the policy is more restrictive and that Sec. 2256.024 makes restriction
conforming, so a reviewer does not read a pass as a near miss.

**A stated conflict is a deficiency, not an absence.** A figure exceeding the cap is
affirmative contradicting evidence. Reporting it as ABSENT would say the policy is silent on
a term it states.

## On trust agreements

Reviewers confirmed that a trust agreement can only be equal to or more restrictive than the
chapter, because the chapter is a floor. So "as further defined by the PFIA **or** such
trust agreement" is not ambiguous: whichever is stricter governs, and both are at least as
strict as the statute. No control is built for it, and ADR 0007's open question is closed.

## Consequences

- Negative element resolution moved from the adapter runner into the evaluator. It is a
  literal search over the document and must give the same answer whether the payload came
  from a live run, a cassette or a cache; the runner being the only place it happened meant
  a replayed payload silently failed it.
- One conformity element became unfalsifiable once its numeric strings were removed and was
  dropped. An element that can never be defeated is not a test.
- A conformity control is now satisfied by silence by design: a policy naming an instrument
  and saying nothing further conflicts with nothing. The restatement gap sits in the
  advisory companion, and a test states both halves so neither is left implicit.

## Revisit when

The review queue is used in anger. If reviewers find themselves re-sorting it, the actions
are the wrong set - they are cheap to change and were chosen from one report's worth of
evidence.
