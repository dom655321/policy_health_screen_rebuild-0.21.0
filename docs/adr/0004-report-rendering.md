# ADR 0004 - Report rendering and the inherited template

Status: accepted (2026-09-06). **Superseded in part by ADR 0010** (no score, health band or score cap; section statuses instead) **and ADR 0011** (section order, governance summary, GTOT paused). Kept as the record of the original decision.

## Context

An HTML/Jinja2 template from an earlier build (the HSAM Policy Health Screen) is available
and already carries an approved visual design, page furniture and internal-use marking.
Reusing it is obviously right. The difficulty is that it was written against a different
domain model, and the mismatch is not cosmetic.

| Template expects | This pipeline has |
|---|---|
| Pass / Partial / Fail / Not Found | CONFORMING / DEFICIENT / ABSENT / NOT_APPLICABLE |
| Critical / High / Moderate / Enhancement | CRITICAL / HIGH / MEDIUM / ADVISORY |
| PFIA + PFCA + GTOT + HSAM frameworks | PFIA only, split into statutory and advisory bands |
| Governance Maturity Index | nothing equivalent |
| Model-authored analysis, recommendation, confidence | register text plus verified spans |
| Critic model, revision count, prompt version | deterministic span verification |
| 0-100 health score capped at 59 on mandatory failure | 0-1 compliance index plus a critical-failure gate |

## Decision

Adapt through a view model rather than by bending either side.

- `pfia.report.viewmodel` is a pure function of the ledger. It performs every vocabulary
  mapping explicitly and in one place, so a reader can recover what the evaluator actually
  decided from what the report says.
- **DEFICIENT splits on score.** Partial where some elements were satisfied, Fail where
  none were and an anti-pattern fired. The register's distinction between silence and
  error is preserved as Not Found versus Fail.
- **Analysis prose is composed, not generated.** Every sentence traces to a control field
  or to a decision the evaluator recorded. No language model contributes a word to the
  report body; the model's only output anywhere in the system is a span and a boolean.
- **Absent frameworks are rendered as absent.** The GTOT index and the maturity index have
  no register in this pipeline. They print "NOT ASSESSED" rather than an empty table or a
  zero, because an empty certification table reads as a clean certification result. This
  is the only substantive edit made to the template, and it is additive.
- **The score cap is retained** because it encodes the right relationship: the statutory
  result is a gate on mandatory-control failure and is never derived from the score.
- **Jinja2 and WeasyPrint are optional extras.** The register, evaluator, adapter and
  ingestion path stay importable with nothing installed. Only rendering needs them, and it
  says so plainly when they are missing.
- **StrictUndefined.** The template carries a comment from the earlier build recording a
  bug where a renamed field resolved to Undefined and printed a fallback string on every
  card while the real quote vanished. Under StrictUndefined that is a render-time error.

## Consequences

- Two fields had to be added to `Finding` to render honestly: `normative_force`, without
  which every control printed as CONDITIONAL, and `counts_toward_score`, without which the
  scored-control figure printed 0/0. Both were latent gaps in the ledger, not template
  problems.
- Confidence is derived from the evidence rather than asserted. A heuristic extraction run
  yields Low confidence on every finding and says why in the review limitations block,
  which is the correct reading of a stand-in extractor.
- The report cannot be produced from a register the pipeline has not authored. That is a
  feature: the disclosure block states that controls absent from the register are not
  evaluated and their absence is not a finding of compliance.

## Revisit when

A GTOT criteria register exists. At that point the framework field on a finding becomes
load-bearing, `gtot_findings` fills, and the alignment ratio becomes meaningful.
