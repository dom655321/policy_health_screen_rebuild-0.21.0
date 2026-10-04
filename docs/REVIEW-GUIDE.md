# Review guide

For the team members who review the register and the model's results. What has been
decided, what is still open, and how to record a verdict so it can be acted on.

## Reviews completed

| Review | Reference | Outcome |
|---|---|---|
| Schedule A element audit | EA-2026-09-27 | Applied as provisional changes (rewordings into "the policy requires ..." form, splits, drops, rebands); every changed element carries its verdict and prior wording |
| Schedule B v2 condition catalogue | TR-2026-10-02 (approved re-review; supersedes TR-2026-09-27 and its follow-up) | 80 conditions active, 49 retired with their verdicts; eight instruments outside the client base marked not reviewed; repo and securities-lending custody tested the same way |
| Core / Context tiering of Schedule A | TIER-2026-09-27 | 19 Core, 17 Context |

## Open for the team

| Item | What is needed |
|---|---|
| Sec. 2256.005(k), the firm's written acknowledgment | Confirm the tier. Unmarked in the approved workbook, kept Core provisionally |
| Ground truth for the bake-off | Correct and mark reviewed the seven `benchmark/ground_truth/*.template.json` files (`docs/MODEL-RUNBOOK.md`, step 3) |
| Ground truth for the benchmark | Transcribe previously reviewed policies, Core controls only (`docs/RUNBOOK.md`, step 4) |
| Three Schedule A queries | Blanket incorporation and Sec. 2256.005(b)(4)(A); whether the enabling Sec. 2256.005(c) should stay reported; which control owns objective ordering |
| Interpretive readings | Counsel's reading of "not less than A or its equivalent" (notch or category) for municipal obligations and securities-lending letters of credit |
| Catalogue adoption | Review the parallel-run report on the recorded Gemini run; every status difference explained before Schedule B v2 is adopted |
| GTOT register | Being completed by the team; switched on when adopted |

## Recording a verdict

Every workbook constrains the verdict column to a closed list, and the note column carries
the reasoning. A free-form verdict cannot be acted on: "too strict" does not say whether to
reword, split, drop or reband, and those are different changes.

| Verdict | Use it when | What happens |
|---|---|---|
| **KEEP** | Right as written | Nothing |
| **REWORD** | Right requirement, wrong wording | Text changes; put the wording in the note |
| **SPLIT** | It tests more than one thing a policy could satisfy separately | Becomes two or more items; say where the line falls |
| **DROP** | It does not state something the statute requires, or it is out of scope | Retired with the verdict attached, kept in the file for the record |
| **REBAND** | Right item, wrong band | Moves between statutory and advisory |
| **NOT_TESTABLE** | It cannot be answered from the policy text | Retired from the review and routed to the evidence request list |
| **ADD** | The statute requires something no item covers | A new item is authored |
| **QUERY** | You need something before you can judge | Comes back as a question |

**Blank means not reviewed.** KEEP means you looked and it is right. Retiring is reversible:
a dropped item is moved back, not rewritten.

For tiering, the column takes **Core** (full element review) or **Context** (one addressed /
not addressed line in the governance summary).

## The questions behind every verdict

1. Does it state something the statute **actually requires**? Good practice written in as a
   requirement has been the register's most common error.
2. Can it be answered from the **four corners of the policy**? Conduct belongs on the
   evidence request list, not in a finding.
3. Is the **band** right? Statutory means the statute requires the policy to contain it;
   advisory means the duty binds whether or not the policy repeats it.
4. Is it **within the firm's business**? Authorized investments and investment management
   provisions are Core; governance and administration are summarized.

## Reviewing the model's results

When a benchmark or bake-off disagreement comes back, classify it before fixing anything:

| Resolution | Fix |
|---|---|
| Item wrong | Register change; the golden-case diff shows its effect |
| Ground truth wrong | Correct the ground truth and note why |
| Reading wrong | The register is right and Gemini misread: a discarded quote, a wrong classification, or no candidate passage found |

## What happens to a returned workbook

Each workbook is applied with its fingerprint recorded, so every register change can be
traced to the file the team approved. Mechanical verdicts are applied directly; QUERY and ADD
come back for discussion first. Applying changes re-blesses the golden cases, and the diff
shows exactly which statuses moved and why.

Read `docs/adr/0009` to `0012` first: they record the catalogue, the move to categorical
statuses, the Core/Context scope, and the model choice, each with the condition that would
overturn it.
