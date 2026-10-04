# Team review TR-2026-09-27: Schedule B v2 condition catalogue

Source: `schedule-b-v2-condition-catalogue_REVIEWED.xlsx` (SHA-256 recorded in the catalogue's
`team_review` block). 129 conditions: KEEP 74, DROP 46, NOT_TESTABLE 7, no verdict 2. No team
notes were recorded, so the reasons below are the reviewer's inference and need confirming.

## How the verdicts were applied

- DROP and NOT_TESTABLE conditions moved to `retired_conditions` on their instrument with the
  verdict attached. They are never evaluated and remain in the file for the audit trail;
  reversing a verdict is moving the entry back.
- NOT_TESTABLE conditions route to the evidence request list: DCD-03/04/05 (new PBC-25),
  MMF-03 (new PBC-26), REP-03/04 (PBC-14), POL-11 (PBC-19). References to dropped conditions
  were removed from the list; PBC-24 (ISD corporate bond forced-sale evidence) had no source
  left and was removed.
- Five instruments lost every condition: MUNICIPAL_UTILITY_HEDGE, MINERAL_RIGHTS_MUNI,
  MINERAL_RIGHTS_JUCO, DECOMMISSIONING_TRUST, ELIGIBLE_ENTITY_HEDGE. They are marked
  `scope: NOT_REVIEWED`; an authorization is reported as not reviewed, never as aligned, and
  never sets the section status. The loader rejects an empty instrument not so marked.
- GTD-01 and MF-01 had no verdict and stay active, flagged `NO_VERDICT`.
- The workbook cleared the note on REP-04; the catalogue note was kept (the condition is
  retired either way).

## Items to confirm

| # | Conditions | Why it matters |
|---|---|---|
| 1 | REP-07 (deposit at time of investment), REP-08 (primary dealer or Texas institution), REP-03/04 (collateral types, value at disbursement) | The parallel run moved REPO from REVIEW_REQUIRED to ALIGNED in all seven cases. 0.18.0 still catches "collateral held by the dealer" and "collateral of any authorized investment"; v2 no longer can. REP-05/06 (pledged; held in the entity's name) were kept, so custody is only partly tested. |
| 2 | SLN-07/08/09 (custody), SLN-10 (counterparty) | Repo keeps pledged and held-in-name; securities lending keeps neither. The two instruments now differ on the same statutory custody triple. |
| 3 | CMO-02 (underlying guaranteed by an agency) | A separate condition of Sec. 2256.009(a)(3) from direct agency issuance (CMO-01). |
| 4 | ICB-07/08 (15% aggregate, 25% single issuer) | Trade-testable concentration limits on ISD corporate bonds; ICB-01 to 06 were kept. |
| 5 | BA-02/03/04 | Sec. 2256.012(2)-(4); dropping leaves maturity and rating only. |
| 6 | DCD-03/04/05, REP-03/04 as NOT_TESTABLE | If the reason is that collateral sits under ch. 2257 (out of scope), that holds for CDs but not for repo: REP-03/04 are Sec. 2256.011 terms and policies commonly state them. |
| 7 | Five special-purpose instruments dropped whole | Consistent with a scope decision (the firm does not manage these mandates). If so, the report should say "not reviewed" on page one for any policy that authorizes them; it now does. |
| 8 | GTD-01, MF-01 | Need a verdict. |

## Follow-up decisions (TR-2026-09-27a)

| Item | Decision | Applied |
|---|---|---|
| 1 Repo | Keep REP-03, REP-04, REP-07, REP-08 | Reinstated. REP-11 (joint-account balance segregation) was not in items 1-6 and stays dropped |
| 2 Securities lending custody | Keep, and test custody the same way as repo | SLN-07 to SLN-10 reinstated. REP-05/06/07 and SLN-07/08/09 now share one custody set (`custody_set: PLEDGED_HELD_DEPOSITED`): same fact keys, mode, obligor and contradiction examples, enforced by a test. Statutory wording is kept per section; the only difference is "selects and approves" (Sec. 2256.011) versus "selects or approves" (Sec. 2256.0115) |
| 3 CMO-02 | Drop: redundant with CMO-01 | Stays retired, rationale recorded |
| 4 ICB-07/08 | Drop: outside the client base | Stays retired, rationale recorded |
| 5 BA-02/03/04 | Keep | Reinstated |
| 6 Collateral | CDs: ch. 2257, out of scope. Repo: in scope | DCD-03/04/05 stay NOT_TESTABLE (PBC-25); REP-03/04 reinstated as tested conditions |
| 7 Five special-purpose instruments | Out: outside the client base | Stay NOT_REVIEWED, reason updated |
| 8 | GTD-01 keep; MF-01 drop | Applied |

Result: 86 active conditions, 43 retired. Parallel run: REPO moves back from ALIGNED to
REVIEW_REQUIRED where the stand-in cannot read collateral terms; v2 still confirms 12 of the
14 0.18.0 conflicts, adds none, and aligns nothing 0.18.0 flagged.

## Superseded by TR-2026-10-02 (approved re-review)

`schedule-b-v2-condition-catalogue_APPROVED.xlsx` re-reviewed all 129 conditions and is now
authoritative: KEEP 79, REWORD 1, DROP 34, NOT_TESTABLE 15 (80 active, 49 retired). Changes
against the follow-up decisions above:

| Condition(s) | Follow-up | Approved |
|---|---|---|
| CMO-02 | Drop (redundant with CMO-01) | Keep |
| DCD-03 to DCD-05 | Not testable (ch. 2257) | Keep |
| MF-01 | Drop | Keep |
| REP-11 | Drop | Keep |
| SLN-10 | Reinstated | Drop |
| SLN-02 | Keep | Drop |
| SLN-06 | Keep | Reworded: "Section 2256.009, .013, .014 or .016" |
| BRD-01, 02, 05; BCD-01, 02, 05 | Keep | Not testable (evidence requests PBC-11, PBC-13) |
| GIC-08 / GIC-09 to 13 | Drop | Keep / not testable (PBC-17) |
| POL-01, 05, 06, 07, 11 / POL-03, 08, 09 | Mixed | Keep / not testable (PBC-19) |
| ICB-01 to 06, IHC-01, IHB-01, IHB-02 | Keep | Drop: ISD corporate bonds and both higher-education instruments are not reviewed |

Repo and securities-lending custody remain congruent (REP-05 to 07 and SLN-07 to 09 kept).
