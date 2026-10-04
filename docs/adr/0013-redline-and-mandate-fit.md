# ADR 0013 - Redline and mandate fit, built from the ledger

**Status:** Accepted · **Date:** 2026-10-01

## Context

The team reviewed mockups of a redline with draft resolution and an internal mandate-fit view
(2026-09-27) and asked for both to be produced from real reviews. The first real run (City of
Richardson, 0.19.2) showed two problems that bear on any generated amendment: draft language
on three Core controls still asked for things the element audit had removed as exceeding the
statute (a pricing source independent of the counterparty, a monitoring cadence and owner, a
per-fund-group maturity), and an extraction file did not record which reader produced it, so
an offline reading could be presented as review-grade.

## Decision

1. **Both outputs read the ledger and the register only.** Nothing appears that the review
   did not find.
2. **Redline scope:** Core Schedule A provisions with CONFLICTS, NOT_ADDRESSED or
   PARTIALLY_ADDRESSED in the statutory band, and authorized-investment conditions that are
   CONTRADICTED (from the Schedule B v2 block, else the 0.18.0 schedule). Core advisory items
   are optional restatements. Findings queued for verification and unsettled conditions are
   held with no language proposed. Context provisions are never amended.
3. **Proposed text is statute-derived.** Each Core control carries `proposed_text`; the
   authorized-investment amendment uses the condition's requirement. Brackets mark what the
   entity decides; `[Entity]` is filled with the entity's name.
4. **Mandate fit compares the strategy with the binding term** the ledger records (the
   stricter of policy and Act; the Act where the policy is silent or conflicts), using the
   evaluator's comparators. An unreadable policy term is "Cannot determine", never "Fits".
   Portfolio-wide figures are reviewer-entered until they are extracted.
5. **Extraction provenance.** `pfia extract` writes `_extraction` (adapter, package, time);
   `review --extraction` uses it, and a payload without it is treated as not review-grade.
6. **Stale draft language corrected** on Secs. 2256.005(b)(4)(B), (D), (F), 2256.005(i) and
   2256.007(d).

## Consequences

- The redline is a draft for reviewer approval; the adjudication file and approval gate that
  turn it into a client document are still to build (`docs/DEFERRED.md`).
- An extraction made before 0.20.0 reads as unlabelled; re-run `pfia extract` for a
  review-grade ledger.
