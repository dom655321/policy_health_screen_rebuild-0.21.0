# How the Policy Health Screen works

*A non-technical explanation for the investment and legal teams. Release 0.21.0.*

---

## 1. What this is

The Policy Health Screen reads the text of an adopted investment policy and reports, provision
by provision, what the policy says against the Texas Public Funds Investment Act. Its focus is
the part of the Act that governs the firm's business: **authorized investments and the
investment management provisions**. Governance and administrative provisions are summarized.

It is a reading tool. It compares one document against a structured list of what the statute
requires and reports what it found and where. Every observation names the passage it rests on.

## 2. What it is not

Stated on the face of every report.

- **Not an audit.** It does not examine holdings, transactions, controls or anything the
  entity does. It reads one document.
- **Not a compliance determination.** Compliance depends on conduct, records and contracts,
  none of which the screen sees. Conduct the screen cannot read is turned into an evidence
  request list, never into a finding.
- **Not legal advice.**
- **Not a score.** There is no index, percentage or weighting anywhere in the output.
  Every result is a status set by fixed rules (section 7).

## 3. Where the requirements come from

Every requirement traces to the statute and nowhere else.

The Act (Tex. Gov't Code ch. 2256, Subchapter A, Secs. 2256.001-2256.026) is held as a
**snapshot**: the official text from the Legislature's file server, pinned on 2026-09-27 with
a fingerprint, and rebuildable byte for byte. Every requirement carries the verbatim statutory
words it rests on, and the build fails if any of them cannot be found in the snapshot. A
weekly check compares the live statute with the snapshot so an amendment is noticed, and
updating the snapshot is a reviewed change, never automatic.

The register also records which entities each section reaches (for example, water districts
under Water Code ch. 36 or 49 are exempt from the training requirements) and which
investments each condition governs (commercial paper conditions apply only if commercial
paper is authorized).

## 4. What is reviewed, and at what depth

The register has three parts.

| Part | What it covers | Depth |
|---|---|---|
| **Authorized investments** (Schedule B v2) | 29 instruments decomposed into 80 active conditions: issuer, rating, maturity, concentration, collateral, custody, counterparty and the like, each one requirement a policy can state, contradict or omit | Full |
| **Investment management provisions** (Schedule A, Core) | 19 controls: objectives, the authorized list, maturity limits, pricing, delivery versus payment, downgrade procedures, strategies, the firm's written acknowledgment, the management contract, quarterly reporting the firm prepares, the broker list, bond proceeds | Full, element by element |
| **Policy governance** (Schedule A, Context) | 17 controls: adoption, annual review, investment officer, disclosure, audits, training | One line each: addressed or not expressly addressed |

The Core and Context tiers were approved by the team (TIER-2026-09-27), and the authorized
investment conditions in the approved re-review (TR-2026-10-02). Eight instruments are outside
the firm's client base and are reported as **not reviewed** if a policy authorizes them:
municipal utility hedging, the two mineral-rights authorities, decommissioning trusts,
eligible-entity hedging, ISD corporate bonds, and the higher-education cash management funds and
corporate debt. GTOT certification analysis is **paused**.

Until the Schedule B v2 catalogue is adopted, the authorized-investments section of the
report is still set by the earlier 53-control instrument schedule, and the catalogue's results
are recorded alongside for comparison (section 10).

## 5. How a policy is read

Five steps. Steps 1, 2 and 5 involve no judgment.

**Step 1 - The document is converted to text**, without a model, with page numbers tracked.
A document that converts to too little text (a scanned policy) is refused rather than
reviewed, because "nothing found" in unreadable text is a confident wrong answer.

**Step 2 - The policy's own list of authorized investments is read** from the document,
including the dominant Texas pattern of one authorizing sentence followed by an enumerated
list. This decides which instrument conditions apply. A policy that authorizes "whatever the
Act permits" without listing types is reported as such.

**Step 3 - For each requirement, the document is searched** for the language that would
address it. No candidate passage anywhere means not expressly addressed, and the search is
the evidence.

**Step 4 - The model reads the candidate passages** and reports facts with verbatim quotes:
whether each element is addressed, and for authorized investments the stated figure and unit,
the rating and number of agencies, whether the rating applies at purchase or continuously,
which statutory alternatives a clause takes, and any contrary language. The model is
**Gemini 3.8 Flash**. It sees the requirement but is asked only to report what the policy
says, never whether the policy complies; the comparison is made afterwards in code. Context
controls are not sent to the model.

**Step 5 - Every quotation is verified against the document.** If a quote cannot be found,
the claim is discarded and the condition reads UNKNOWN. Every observation reduces to "this
passage, at this page, says this", never "the software concluded this".

## 6. Where judgment enters, and where it does not

Only step 4 involves judgment, and it is narrow: reading what a passage says. Everything after
it is fixed rules in code:

- **Comparisons are arithmetic.** A stated maturity is compared with the statutory cap after
  unit conversion; a rating is compared on a cross-agency scale (A-1 = P-1 = F1); a permitted
  list is checked against the statutory list. A policy capping commercial paper at 270 days
  where the Act allows 365 is **more restrictive than the Act**, and Sec. 2256.024 makes a
  more restrictive policy conforming. Restriction is never a finding.
- **Statutory alternatives stay together.** Commercial paper may be rated by two agencies, or
  by one agency with a bank letter of credit; a policy taking either path conforms, and only a
  path outside both is a conflict.
- **Ambiguity is not resolved by guessing.** A figure within three days of a limit after an
  approximate unit conversion, a percentage on a different base than the statute's, or a
  rating that is not on any agency's scale reads UNKNOWN.
- **Known problem phrasing** (for example "delivery versus payment where practical") is a
  literal search, never a judgment call. Generic phrases such as "as needed" count only when
  the subject of the requirement appears in the same or the preceding sentence.

## 7. How the result is reached

**Each item** gets one status:

| Status | Meaning |
|---|---|
| **Addressed** | The policy states the requirement |
| **Addressed (more restrictive)** | The policy states a narrower term than the Act |
| **Addressed by reference** | The policy incorporates the Act for that provision ("as further defined by the PFIA") |
| **Addressed in part** | Some elements stated, others not |
| **Not expressly addressed** | Not stated; where the statute requires the policy to state it, an addition is recommended |
| **Stated terms differ from the Act** | A stated term the statute does not permit; a revision is recommended |
| **Confirmation required** | Applicability turns on a fact about the entity not yet supplied, or the reading could not be settled |
| **Not applicable / Not reviewed** | Does not reach this entity, governs an investment the policy does not authorize, or is outside the firm's client base |

**Each section** gets one status, by fixed rules applied in order, first match wins:

1. Any item whose applicability is unresolved: **Review in progress**
2. Any stated term that differs from the Act (statutory items): **Revisions recommended**
3. Any statutory requirement not expressly addressed or addressed in part: **Additions recommended**
4. Otherwise: **Addresses the provisions reviewed**

The governance summary never sets a status; it lists what the policy addresses. Severity
orders the items on a page and never decides a status. Counts of items per status are shown;
a count describes, it is not a score.

## 8. Two kinds of requirement, kept apart

**Statutory items** are those the statute requires the policy itself to contain (for example
Sec. 2256.005(b): "the investment policies must include"). A gap is a gap in the document.

**Advisory items** are duties that bind whether or not the policy repeats them, such as the
standard of care in Sec. 2256.006. A policy silent on one has not breached anything; these are
reported separately and never set a section's status. The band is decided per element, so a
control can carry both.

For authorized investments, Sec. 2256.005(b)(4)(A) requires the list of types, not a
restatement of each type's conditions, which bind by force of Sec. 2256.024. So a condition
the policy does not restate is reported as **not restated** and never changes the instrument's
status; only a stated term that conflicts with the Act does.

## 9. What keeps it honest

- Every quotation is verified, and unverifiable claims are discarded.
- Every observation cites a page.
- Unanswered questions stay unanswered and are reported as requiring confirmation.
- Coverage is stated: sections not reviewed are listed, so silence never reads as a clean result.
- Every result is reproducible: the ledger records the document's fingerprint, the register
  version, the software version and the reader used, and a recorded run's cassettes record
  the exact model that answered each request, so the run replays exactly.
- The model never decides conformity, and a failure to read reads UNKNOWN, never aligned.

## 10. Known limits

1. **Not yet validated against the team's past reviews.** Until the benchmark (`docs/RUNBOOK.md`)
   and the thinking-level bake-off (`docs/MODEL-RUNBOOK.md`) are run on reviewed policies,
   every result is a candidate for review rather than an established finding.
2. **The authorized-investment catalogue is proposed.** It runs alongside the earlier
   instrument schedule and is adopted only after a recorded model run with every difference
   explained.
3. **One model, one reading.** Two-reader cross-checking needs a second, independent
   provider and is not in use.
4. **Ch. 2257 (Public Funds Collateral Act) is not reviewed.** Certificate-of-deposit collateral
   under Sec. 2256.010(a)(2) and repurchase agreement collateral under Sec. 2256.011 are reviewed,
   because they are Investment Act terms.
5. **GTOT certification is paused**, and governance provisions are summarized only.
6. **Interpretive readings are labelled**, for example "not less than A" read at the notch
   (A- falls below), pending counsel.

## 11. How to read a report

Page one is written to be shareable: the result, the status of each section in the order
authorized investments, investment management provisions, governance summary, the leading
items for consideration, and the scope statement *"Governance and administrative provisions
are summarized, not reviewed in detail."*

Everything after page one is working material for internal use: item identifiers,
element-by-element results, the passages relied on, unreviewed draft language, and the
reviewer work queue. The client-approved Summary and Checklist, and the optional redline, are
produced only from reviewer-approved findings (the presentation step of the build). The
redline (`pfia redline`) is generated as a draft for that approval: it proposes statute-derived
language only for Core provisions and authorized-investment terms, and holds any item whose
reading needs verification. Mandate fit (`pfia mandate-fit`) is internal only; see
`docs/OUTPUTS.md`.
