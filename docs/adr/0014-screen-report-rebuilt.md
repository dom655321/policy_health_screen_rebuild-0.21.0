# ADR 0014 - Screen report rebuilt on the current model; reading-reliability guards

**Status:** Accepted · **Date:** 2026-10-04

## Context

The first live runs (City of Richardson, Harris County) showed the screen report still
rendered the pre-0.19 design: "HSAM Policy Health Screen" branding, audit vocabulary on the
internal pages (DEFICIENT, CRITICAL, FAIL, "Deficiency register"), Context provisions in the
leading items and as full cards, no Schedule B v2 results, and a "Practice items" section from
the dropped best-practice band. The Harris County run also showed a more serious problem: the
stdlib PDF reader split kerned words ("q uarter ly", "transaction s"), quality still read OK,
the authorized list was read as two instruments, and mandate fit reported six false Blocks.

## Decision

1. **The screen is rebuilt** on the view layer the redline and mandate fit use
   (`screen_context`, `screen.html`, shared `outputs.css`). Page one: result, section tiles in
   the ADR 0011 order, scope statement, leading items (Core statutory items and conflicting
   instrument conditions). Working paper: work queue by kind of check, authorized investments
   condition by condition, Core cards element by element with proposed language, governance
   summary, restatement items, evidence requests, provenance. No score and no audit vocabulary
   anywhere in the document (tested). Earlier designs remain as `--template screen-0.19` and
   `legacy`.
2. **Kerned fragments.** The stdlib reader treats a zero-vertical Td or a baseline-preserving
   Tm as a same-line move and joins kerned fragments into words. Quality now counts
   word-splitting artifacts and degrades the document, naming the remedy (pypdf or poppler).
   `pip install -e '.[pdf]'` installs pypdf.
3. **Reliability guard.** When extraction quality is not OK or no enumerated authorized list
   was located, every output says so; mandate fit reports instruments missing from the list as
   Cannot determine, never Blocks.
4. **Redline:** a conflict resting on a verified literal match is proposed even if another
   element's quote was discarded (not for an offline reader).
5. **Versions:** register versions 2026.10.04; catalogue 0.2.0-proposed.

## Consequences

Ledgers produced before 0.21.0 render in the new design. A Harris County re-run with pypdf
installed is needed before its authorized-investment and mandate-fit results are relied on.
