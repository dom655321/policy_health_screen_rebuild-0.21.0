# Security and client-data handling

## The rule

**No client material in this repository.** Not policy documents, not ledgers, not
cassettes, not extraction caches. `.gitignore` blocks `engagements/`, `.cache/` and any
`cassette.json` outside `tests/golden/`, but the rule is the rule and the ignore file is
only a backstop.

Every fixture in `tests/` is synthetic and written for the purpose. If a real policy is
ever needed as a fixture, it must be one already public and it must be recorded as such.

## Where client material goes

```
engagements/<client>/policy.pdf          the document as received
engagements/<client>/profile.json        the answered entity profile
engagements/<client>/ledger.json         the work product
engagements/ground-truth/<case>.json     transcribed prior reviews
```

Keep that tree outside the repository, or inside it and ignored, depending on where your
records policy says client documents live. Either works; committing it does not.

## What holds client text

| Artifact | Contents | Retention |
|---|---|---|
| Extraction cache | Verbatim policy quotes and model responses | 30 days, engagement-scoped, purge on close. Off unless `--cache` is passed |
| Cassettes | Recorded model responses, including quotes | Synthetic and public documents only |
| Derived text | Extracted policy text | Delete after the run; reproducible from source plus backend plus register version |
| Finding ledger | The work product | Firm advisory workpaper retention |

`pfia purge <paths> --yes` deletes derived material. It is a dry run without `--yes`.

**The ledger is the only artifact that needs to survive.** Source, derived text and cache
are all reproducible from it plus the original document, so deletion elsewhere can be
aggressive.

## Third-party model transmission

An adopted Texas investment policy is a public record - §2256.005(a) requires adoption by
rule, order, ordinance or resolution of a governing body, which brings it within the
Public Information Act. Confirm that with counsel, but if it holds, the source document is
not the sensitive asset. The findings, the engagement itself, draft or unadopted policies,
and board packets are.

Live adapters send policy text to a third party. Before a real document goes through, one
of these must be settled:

1. A zero-data-retention API tier with a signed DPA and a per-engagement key. Adequate for
   adopted policies.
2. A self-hosted model for drafts and board packets. The adapter layer makes this a
   constructor change.
3. Deterministic-only mode. The sweep proves absence without a model call and roughly a
   third of controls resolve that way. Not a review, but usable for triage on material
   that cannot leave.

## Reporting a problem

Raise it with the register owners named in `CODEOWNERS`. A defect that causes a finding to
be wrong in a client's favour is as serious as one that is wrong against them.
