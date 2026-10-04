# ADR 0001 - Normalized register with a separate instrument schedule

Status: accepted (2026-09-05)

## Context

Reviewing a public entity investment policy against PFIA requires mapping roughly 175
discrete normative propositions to policy language. Three structures were considered.

| Option | Shape | Rejected because |
|---|---|---|
| A. Flat control array | One JSON array, conditions denormalized per control | Applicability logic duplicates across ~40 training and reporting controls; amendments touch many nodes |
| B. Normalized register | `controls` + `predicates` + `entity_classes`, joined by ID | selected |
| C. Statutory graph + overlay | Node graph of the chapter with controls as annotations | Overbuilt for a first-pass tool; adds an operational dependency to a SharePoint/Teams deployment |

## Decision

Build B, structured so that C is a later projection rather than a rewrite. Authorized
investment-type controls live in a separate schedule keyed to the extracted authorized
instrument list, sharing the same schema and evaluator.

## Consequences

- Predicates are written once and referenced. Session-law amendments become single-node
  edits plus a snapshot diff.
- Dangling references fail at load time rather than evaluating to false during a client
  review. `_validate_references` is the gate.
- A loader and reference resolver are required; the raw JSON is less readable than a flat
  file. A flattened build artifact can be emitted for the report appendix.
- The instrument split keeps the coverage matrix legible and prevents ~120
  activation-gated controls from distorting the composite score.

## Revisit when

Cross-reference queries ("what breaks if Sec. 2256.009(a)(1) is amended") become a
routine part of the workflow. That is the point at which the graph projection earns its
operational cost.
