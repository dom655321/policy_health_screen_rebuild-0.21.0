# ADR 0005 - Three unknowns, made structural

Status: accepted (2026-09-06)

## Context

Three things stood between the register and a run against a real policy, and all three had
the same shape: the system could not distinguish a determination from the absence of one.

1. **The authorized-investment set was supplied by hand.** Every Schedule B control gates
   on it, so the tool was scoring the reviewer's belief about what the policy authorizes
   rather than the policy.
2. **The entity profile was hand-authored with no validation.** Twelve controls gate on it
   and several gate decisively. Two-valued logic answered "no" for every unanswered
   question, silently dropping controls out of the applicable set.
3. **Register coverage was invisible in the output.** A review scoring 49 controls and
   saying nothing about the rest of the subchapter invites the reader to assume the rest
   was examined and found clean.

Each failure produces the same artifact: a confident result over a question nobody
answered.

## Decision

**A third truth value, carried end to end.** `jsonlogic` gains UNKNOWN with Kleene
semantics - a definite False still decides a conjunction, a definite True still decides a
disjunction, and anything else propagates. UNKNOWN raises on `bool()` so it cannot be
collapsed by accident. It resolves to a new verdict, APPLICABILITY_UNRESOLVED, which is
excluded from both indices and reported separately from NOT_APPLICABLE.

**The questionnaire is derived from the register.** Required entity facts are read out of
the predicates the loaded registers reference; `fields.json` supplies only the wording. The
two are reconciled in both directions at load time, so a new predicate demands its question
and a stale question fails the build. An unanswered field becomes UNKNOWN rather than
false, and the finding names the fact that blocked it.

**The authorized-investment set is read out of the document.** A lexicon proposes
candidates with verified offsets; sentence polarity decides whether a passage authorizes or
excludes. Three outcomes matter: enumerated, blanket incorporation, and section not
located. The last two leave the set open, and an instrument absent from an open set is
UNKNOWN rather than unauthorized. Blanket-incorporation phrasing is read from the
anti-pattern library of TX-PFIA-2256.005-b-4-A-001 rather than restated, so the two cannot
drift.

**Coverage is computed and entity-aware.** The section inventory of Subchapter A is
independent of what the register covers, so the gap is arithmetic rather than rhetoric.
Sections scoped to other entity classes are not reported as gaps, because noise buries the
gaps that do apply.

## Consequences

- An empty scoring pool now returns None rather than 1.0. A perfect score over zero
  controls was the most misleading number the system could emit; it is produced by exactly
  the conditions above and reads as a clean bill of health.
- The register gate is three-valued too. An unanswered Sec. 2256.004 question no longer
  reports the entity as excluded from the subchapter.
- Detection reproduces the hand-written fact files exactly on the enumerated fixtures,
  which is the evidence that it can replace them. On the blanket-incorporation fixture it
  scores 29 controls rather than 37, with 13 unresolved - the correct answer, and one the
  hand-supplied facts concealed.
- Polarity masking is load-bearing: without it "not authorized" satisfies the "authorized"
  cue by substring, and a policy that expressly excludes the prohibited mortgage
  derivatives reads as authorizing them. That is a fabricated CRITICAL finding, and it is
  pinned by a regression test.

## Revisit when

Ground truth arrives. The lexicon is the component most likely to need widening, and the
first real policies will show whether `no_instruments_recognized` fires on lexicon gaps
often enough to warrant a model confirmation pass by default rather than as an option.
