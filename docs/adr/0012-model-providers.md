# ADR 0012 - Model providers, two-reader mode, and the bake-off

**Status:** Accepted (selection pending the bake-off) · **Date:** 2026-09-27

## Context

The rebuild removed the model from PDF text extraction (deterministic ingest, ADR 0003) and
from every comparison (ADR 0009). What remains is reading short passages and returning typed
facts with verbatim quotes. Quote verification catches invented text; it cannot catch a
correct quote with a wrong classification. The costliest error is a false conflict, because
it becomes "Revision recommended" on a client document.

## Decision

1. **Providers over plain HTTP** (Anthropic Messages, Gemini generateContent), no SDK. The
   Schedule B v2 contract (`{"conditions": ..., "activation": ...}`) is parsed separately
   from the Schedule A elements contract; a truncated conditions response is refused rather
   than salvaged. Provider-specific request settings come from `PFIA_*_EXTRA_BODY`.
2. **No default model.** A live adapter requires an explicit model ID.
3. **Provenance.** Each response's served model and token counts are captured; cassettes
   record them with the prompt's SHA-256, never credentials.
4. **Two-reader mode** (`second_adapter`): each Schedule B v2 condition is asked of two
   readers; only facts both agree on after quote verification reach the evaluator. A
   disagreement, including one reader silent, reads UNKNOWN. No tie-breaker model.
5. **Context controls never reach a live model** at SUMMARY depth (ADR 0011); they are
   answered offline, with a cache key that names the answering adapter.
6. **Bake-off** (`scripts/bakeoff.py`) scores candidates against reviewed ground truth on
   false conflicts, missed conflicts, UNKNOWN rate, quote verification, stability across
   repeats, failures and cost, and applies a fixed selection rule.

Candidates: Claude Sonnet 5.5 (proposed primary), Claude Haiku 4.5, Claude Opus 5.5
(ceiling reference), Gemini 3.8 Flash, and Sonnet 5.5 + Gemini 3.8 Flash as two readers.

## Consequences

- The offline stand-in fails the default thresholds (UNKNOWN 18%, quote verification 73% on
  the first dry run), which is the intended behaviour: it is plumbing, not a candidate.
- Golden cases record `context_summary_answers`; live model calls per case fell by the
  number of Context controls that reached extraction.
- Schedule A two-reader mode is not built: an unsupported element reads NOT_ADDRESSED, not
  UNKNOWN, so disagreement there needs its own design.

## Addendum (2026-09-30, 0.19.1): Gemini 3.8 Flash as the working reader

Claude calls are unavailable in the current environment, so testing proceeds on
gemini-3.8-flash. The Gemini adapter was written for 2.x models and set temperature 0; for
Gemini 3.x Google recommends leaving temperature at its default, so 3.x requests now omit it
and set reasoning effort with `thinkingLevel`. `PFIA_ADAPTER`/`PFIA_MODEL` are explicit
configuration, consistent with decision 2 (no built-in default). The selection rule and
two-reader design are unchanged; Claude candidates return to the bake-off when calls work.
