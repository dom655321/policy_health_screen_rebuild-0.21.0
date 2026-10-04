# ADR 0002 - Extraction seam and evidence verification

Status: accepted (2026-09-06)

## Context

The register is dense enough to review a real policy, but the only extractors were a
deterministic keyword baseline and a replay stub. A production path needs a model, and a
model introduces three failure modes that a compliance deliverable cannot absorb:

1. **Fabricated evidence.** A model asked to cite supporting text will sometimes return a
   plausible paraphrase that does not appear in the document.
2. **Unreliable absence.** Asked whether a document is silent on a subject, a model
   answers inconsistently, and the cost of asking scales with every control.
3. **Vendor coupling.** The firm may mandate a different model next quarter. A pipeline
   coupled to one vendor's SDK becomes a migration project rather than a config change.

## Decision

Split extraction into a deterministic layer and a model layer, with the deterministic
layer holding every load-bearing decision.

- **The model is asked one question per control**: which required elements does this
  window support, quoted verbatim, plus any facts the control names. It is never shown
  the verdict vocabulary, severity or weight.
- **Quotes are verified, not trusted.** The runner locates the quote in the document and
  derives the offsets itself. An unlocatable quote is discarded, the element is marked
  unsupported, and the discard is written into the trace.
- **Absence is proved mechanically.** The runner sweeps the full document for every search
  directive. No match anywhere means ABSENT with the sweep as evidence and no model call.
  The model only ever confirms presence.
- **Anti-patterns never reach the model.** They are literal searches; asking a model
  invites paraphrase matching, which is the failure the library exists to prevent.
- **Prompts are generated from the control.** No prompt text is maintained separately, so
  there is no second artifact to drift from the register.
- **Providers are plain HTTP.** No vendor SDK; zero runtime dependencies preserved.

## Consequences

- Every finding reduces to "the document contains X at offset N", which survives a client
  challenge in a way that "the model asserted X" does not.
- Model spend falls: absence and prohibition controls resolve without a call, and the
  content-addressed cache makes re-runs free.
- The heuristic adapter is deliberately stricter per element than the old keyword
  baseline, so golden scores moved down on first blessing. That is the pipeline being
  more discriminating, not the policies being worse.
- Two artifacts now must move together on a register edit: the control and its golden
  expectation. `make golden` names the transitions.

## Revisit when

Cassettes recorded from two different live providers disagree on the same case. That
disagreement is the measurement this architecture exists to make possible, and it is the
signal for whether element assertions need tightening.
