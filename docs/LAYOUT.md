# Repository layout

The organising principle: **code, data, and client material are three different things
with three different lifecycles**, and the layout keeps them apart.

Code changes on a release cycle. The register changes on a legislative cycle and is
reviewed as a legal document, not as software. Client material should never enter the
repository at all.

## Root

Project-level configuration and the entry document. **No code, no data.**

```
README.md            what this is and how to run it
pyproject.toml       package metadata, optional extras, packaging
Makefile             every operation anyone needs to run
.gitignore           keeps derived client material out
.github/workflows/   CI
```

Worth adding for a company repository:

```
LICENSE              internal or proprietary notice
CHANGELOG.md         one entry per register version; the legislative history matters here
SECURITY.md          where to report an issue, and the client-data handling rule
CODEOWNERS           the register needs a named reviewer, not just any approver
```

## Directories

| Directory | Holds | Rule |
|---|---|---|
| `src/pfia/` | The importable package. All library code | Nothing here reads a hard-coded client path |
| `src/pfia/conditions/` | Schedule B v2: catalogue loader, rating scales, deterministic evaluator, wiring, offline stand-in | The model reports facts; every comparison is made here |
| `data/registers/policy-content/` | Schedule A: 36 controls, each tagged Core or Context | Reviewed as a legal document; every change is a diff someone signs off |
| `data/registers/instrument-schedule/` | The 0.18.0 instrument schedule (53 controls) | Sets the authorized-investments status until Schedule B v2 is adopted |
| `data/registers/instrument-conditions/` | Schedule B v2 catalogue (proposed) and its detection lexicon supplement | Every condition's quote must appear in a section it cites |
| `data/registers/evidence-requests/` | The prepared-by-client request list | Never sets a status; Context and out-of-scope requests paused |
| `data/registers/gtot-criteria/` | GTOT register | Paused: loads only when named explicitly |
| `data/registers/*.json` | Predicates, entity classes, instrument lexicon, coverage inventory | As above |
| `data/mandates/` | Example strategy parameters and policy-limits files for mandate fit | Real strategy files are the firm's; client limits live under `engagements/` |
| `data/profiles/` | Entity profile question metadata and non-client example profiles | Real client profiles live outside the repo |
| `data/sources/` | Statute snapshot, pinned raw HTML (`raw/`), `MANIFEST.json` fingerprints | Refreshed only by a reviewed `fetch_statute.py --fetch` commit |
| `data/ground-truth/` | The benchmark transcription template only | Real transcriptions name client documents and live outside the repo |
| `benchmark/ground_truth/` | Bake-off ground truth for the synthetic golden policies | Client policies go in `benchmark/policies/`, which is git-ignored |
| `schema/` | JSON Schemas for each register | Enforced by `make schema` |
| `scripts/` | Operator entry points that import the package | Not importable, not installed |
| `tests/` | Test suite, synthetic fixtures, golden cases | All fixtures synthetic |
| `docs/` | Setup, runbooks, methodology, review guide, ADRs, audit records | ADRs are the record of why; `docs/audit/` records each team review |

Root also holds `bakeoff.gemini-flash.example.json` and `bakeoff.example.json` (copy to the
git-ignored `bakeoff.json`) and `.env.example` (copy to the git-ignored `.env`).

## Not everything Python goes in `src/pfia/`

Only code that is *imported* belongs in the package. The distinction is whether something
is a library or an operator tool:

- **`src/pfia/`** — imported by other code. `loader`, `evaluate`, `instruments`, `profile`,
  `coverage`, `benchmark`, `ingest/`, `adapter/`, `conditions/`, `report/`. `cli.py` is here because it is
  the package's own entry point, wired through `pyproject.toml`.
- **`scripts/`** — run by a person, never imported by the package. `bakeoff.py`,
  `benchmark.py`, `compare_schedule_b.py`, `fetch_statute.py`, `golden.py`,
  `verify_sources.py`, `validate_schemas.py`, `audit_register.py`, `export_review.py`,
  `export_catalogue.py`,
  `make_test_pdf.py`. Each adds `src/` to the path and imports the package.

The one exception: `tests/test_golden.py` imports `scripts/golden.py`, because the golden
comparison logic and the golden test are the same logic and duplicating it would let them
diverge.

## Where client material goes

Nowhere in this repository. The `.gitignore` blocks `engagements/`, `.cache/`, `.env`,
`bakeoff.json`, `bakeoff-results/`, `benchmark/policies/` and any cassette outside
`tests/golden/`, because caches and cassettes contain verbatim policy text, ledgers contain
findings, and `.env` holds the API key.

The convention the runbook assumes:

```
engagements/<client>/policy.pdf          the document as received
engagements/<client>/profile.json        the answered entity profile
engagements/<client>/cache/              model responses (verbatim text; purge after use)
engagements/ground-truth/<case>.json     transcribed prior reviews
engagements/recorded-run/                the recorded Gemini run (cassettes)
```

Keep that tree outside the repository, or inside it and ignored, depending on where your
records policy says client documents live. Either works; committing it does not.

## The register is data, not package data

`data/registers/` is deliberately outside `src/pfia/`. It is reviewed on a legislative
cycle by people who are not reading Python, and burying it in a package directory makes
that review harder for no benefit.

The cost is that an installed wheel has no register. `cli._default_root()` resolves in
order: `PFIA_REGISTER_ROOT`, then the repository layout, then a packaged copy if one was
built. If you later want a standalone install, add

```toml
[tool.setuptools.package-data]
"pfia" = ["data/registers/*.json", "data/registers/*/*.json"]
```

and copy `data/registers/` into `src/pfia/data/` at build time. Until then this is a
repo-run tool, which is the right shape for something whose primary artifact is under
review.
