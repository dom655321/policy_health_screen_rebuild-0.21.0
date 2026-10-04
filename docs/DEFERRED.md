# Deferred decisions

Every item here is a decision, not an oversight. Each says what was deferred, why, and what
would trigger taking it up. Several are drawn from the "revisit when" clause of an ADR,
which is where the condition was recorded at the time the choice was made.

Nothing on this list blocks the immediate tasks or the register review.

---

## Register depth

### 1. Sec. 2256.016 pool disclosure and reporting items
**Partly resolved in 0.19.** The Schedule B v2 catalogue tests the pool's operating
requirements as separate conditions (POL-02 to POL-11: invests only in authorized investments,
offering circular, confirmations, monthly report, daily mark-to-market, $1.00 NAV band,
advisory board, continuous AAA rating, audited financials). The thirteen offering-circular
items and eleven monthly-report items are **not** itemized; they bind the pool, not the policy,
and are requested as evidence (PBC-19).

**Trigger.** Reviewers wanting item-level pool findings, or `unmapped_findings` in a benchmark
showing prior reviews raised specific disclosure gaps.

### 2. Item-level incorporation clauses
**Deferred.** An incorporation clause in the sentence introducing an authorized-investment
list governs every item under it and satisfies the completeness controls. The same words
inside a single item govern that item alone, and are recorded with `applies: false` rather
than applied.

**Why.** Mapping an item-level clause to the single instrument it sits with is contained
work. Over-generalising it would pass statutory conditions for instruments the clause never
mentioned, which is a worse error than not applying it at all.

**Trigger.** An item-level clause appearing in a policy where it changes a finding.
Recorded in ADR 0007.

### 3. Sec. 2256.005(h) unreconciled amendments
**Deferred as interpretive.** Two 1997 amendments to Subsection (h) remain unreconciled in
the official code and point in different directions. The control carries both texts under
`source_text_variants` with `interpretive: true`, applies the broader ch. 1421 text, and
reports the conflict rather than resolving it.

**Why.** A register cannot resolve a legislative conflict. Reporting it is the correct
output.

**Trigger.** The legislature reconciling the subsection, or counsel taking a firm position
the register should follow.

### 4. Remaining sections classified as not testable
**Deferred with reasons recorded** in `data/registers/coverage.json`:
- Secs. 2256.001, 2256.002 - definitional
- Sec. 2256.004 - consumed by the applicability predicate rather than by a control
- Sec. 2256.024 - consumed as a rule the evaluator honours: a policy stricter than the
  chapter is never reported as a conflict
- Sec. 2256.022 - directs a risk assessment by the state auditor; no obligation a policy can
  evidence

**Why.** Each classification is a review decision, and recording it in data means it can be
challenged rather than argued about.

**Trigger.** A reviewer disagreeing with any classification. Change the entry and the
coverage report follows.

---

## Additional authority layers

### 5. GTOT certification criteria
**Paused (ADR 0011).** `data/registers/gtot-criteria/` is marked `status: paused`: it never
loads unless named explicitly, and GTOT is absent from every output rather than shown as
"Not assessed". The team is completing the register.

**Shape to follow when it is adopted.** GTOT's own fields (criterion reference, checklist
edition, verbatim criterion text, Met / Not met / Not applicable), not statute fields; a
`satisfied_by` link from each criterion to the PFIA requirement or condition it repeats, so
one reading serves both and the two sections cannot disagree on the same sentence; and a
policy-text form of each criterion, which the redline needs. A test fails the build if the
register is adopted while any placeholder remains.

**Trigger.** The team adopting the register: change `status` to `adopted`.

### 6. Chapter 2257, the Public Funds Collateral Act
**Out of scope.** Collateral requirements of ch. 2257 itself are not reviewed. The Investment
Act's own collateral terms are: certificates of deposit secured by obligations (Sec.
2256.010(a)(2), conditions DCD-03 to DCD-05) and repurchase agreements (Sec. 2256.011,
REP-03 and REP-04). Evidence of the collateral actually held is requested (PBC-14, PBC-25).
Every report says ch. 2257 was not reviewed.

**Trigger.** A client asking for collateral compliance.

### 7. Local charter and bond-order overlays
**Deferred.** A fourth authority tier. Sec. 2256.024 makes the subchapter cumulative, so a
charter or bond order can only narrow - and the evaluator already never reports restriction
as a conflict.

**Why.** The overlay would change what counts as *conforming for this entity*, not what the
statute requires. It needs an entity-specific document set the register does not ingest.

**Trigger.** An engagement where a bond order is materially stricter than the chapter and
the client wants the tighter standard tested.

---

## Measurement

### 8. Two-reader mode in use
**Built, not in use.** Two-reader mode (ADR 0012) asks two readers about every Schedule B v2
condition and keeps only what both agree on. It needs a second, independent provider: two
readings from the same model share the same errors. With Gemini 3.8 Flash as the only working
reader it stays off.

**Trigger.** A second provider available (Claude calls restored, or another provider added).

### 9. Two-reader mode for Schedule A Core
**Not built.** For Schedule A, a disagreement would make an element unsupported, which reads
NOT_ADDRESSED rather than UNKNOWN and could produce a false "Additions recommended". It needs
its own design before it is safe.

**Trigger.** Item 8, plus a benchmark showing misread Core elements.

### 10. Live validation at scale
**Starting.** The Gemini adapter was written to Google's documented request and response
format and tested with a substituted transport; `adapter-check` is the first real call. Any
response shape found in the bake-off is added to the tests rather than fixed ad hoc.

**Trigger.** The first bake-off run.

---

## Ingestion

### 11. OCR backend
**Deferred.** A scanned policy is refused by the quality gate rather than reviewed, because
near-empty text produces a confident "nothing found" for a document nobody has read.

**Why.** Refusal is the safe default and no client policy has yet required OCR.

**Trigger.** A scanned policy arriving in an engagement. Per ADR 0003 its output should be
marked DEGRADED by default rather than trusted at the same level as extracted text.

### 12. Statute snapshot refresh
**Resolved in 0.19.** The chapter text is fetched from the Legislature's file server
(`scripts/fetch_statute.py`), pinned with fingerprints in `data/sources/MANIFEST.json`, and
rebuildable offline (`make statute-rebuild`). A weekly job (`statute-drift`) compares the live
text with the pinned snapshot and fails when they differ. Refreshing the snapshot stays a
reviewed commit (`--fetch`), never automatic. The 90th Legislature convenes in January 2027.

---

## Deployment

### 13. SharePoint / Teams deployment
**Not started.** The tool is a repo-run command line application.

**Trigger.** Reviewers other than the register authors needing to run it themselves. Until
then, running it centrally and sharing the ledger is simpler and keeps client material in
one place.

### 14. Non-editable install
**Deferred.** `PFIA_REGISTER_ROOT` resolution and a packaged-copy fallback are implemented
and tested, but no wheel has been built or installed in the target environment.

**Why.** The register is reviewed as data on a legislative cycle and lives outside the
package. Repo-run is the right shape while it is under review.

**Trigger.** Distribution to a machine that will not hold the repository.

---

## Scope and adoption

### 15. Adopt Schedule B v2; retire the 0.18.0 instrument schedule
**Gated.** The catalogue is proposed and runs alongside the 53-control schedule. Adoption
needs a recorded Gemini run over the golden and benchmark policies and every status
difference in `scripts/compare_schedule_b.py` explained.

### 16. Out-of-scope instruments
**Decided (TR-2026-10-02).** Municipal utility hedging, mineral-rights funds (municipal and
junior college), decommissioning trusts, eligible-entity hedging, ISD corporate bonds, and the
higher-education cash management funds and corporate debt are outside the client base and
report as not reviewed. Their conditions are kept, retired, for a later expansion.

### 17. Client outputs
**Partly built (0.20.0).** The redline and mandate fit are generated from the ledger
(`docs/OUTPUTS.md`). Still to build: the reviewer adjudication file and approval gate, the
client Summary and Checklist, insertion points per finding for the redline, and extraction of
portfolio-wide figures (maximum maturity, weighted average maturity) for mandate fit.

**Trigger.** Team decisions on the redline and mandate fit; the presentation step.

---

## Product surface

### 18. Client-mode marking and product name
**Open, and needs a decision rather than engineering.** The page-one chip reads INTERNAL USE
ONLY by default; `--distribution client-draft` renders "Draft - pending compliance review"
as a placeholder. Since 0.21.0 all three documents use "Investment Policy Review" (Policy Screen,
Proposed Amendments, Mandate Fit) as the eyebrow and running header; the HSAM name is retired.

**Trigger.** Compliance and legal settling the approved client marking and the product name.
Both are single strings.

### 19. Logo placement
**Deferred.** No logo asset was supplied and the concepts did not include one. Placement is
prepared in the cover header and the running header.

### 20. Client-facing derivative beyond page one
**Deferred.** Page one is written to be shareable. A fuller client document would be a
different artifact: no unreviewed draft language, no register identifiers, no confidence
labels, and the interpretive items stripped out.

**Trigger.** Compliance approving page one and asking for more than a cover.
