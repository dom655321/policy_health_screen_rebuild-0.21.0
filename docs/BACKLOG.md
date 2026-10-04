# Engineering backlog

## Cleared in 0.19

| Item | What was done |
|---|---|
| Repository and first commit | Clean history from the 0.18.0 baseline; tags `v0.18.0`, `v0.19-full-scope`, `v0.19.0`, `v0.19.1` |
| Statute snapshot and law-sync gate | Snapshot committed and reproducible (`make statute-rebuild`); CI law-sync gate is blocking; weekly `statute-drift` job |
| Schema validation | Every register validated against the schema its `$id` names (`make schema`) |
| Loader strictness | A missing band is a load error; cross references are validated |
| Numeric scoring | Removed end to end (ADR 0010) |
| Gemini 3.x requests | No temperature, `thinkingLevel`, 32k output ceiling, thought parts ignored, blocked prompts named (0.19.1) |
| Provider robustness | Retries with backoff on 429 and 5xx; HTTP errors carry the provider's message; deep-merged extra settings |
| CLI | Adapter errors print one line and exit 2 instead of a traceback; `--out` creates its directory |

## Open

| Item | Notes |
|---|---|
| Claude adapter | Calls are failing in the operator environment. The error message now names the cause; diagnose from `pfia adapter-check --adapter anthropic --model claude-sonnet-5-5` before Claude rejoins the bake-off |
| `CODEOWNERS` handles | Placeholders. An unresolvable entry silently approves nothing; replace them before enabling branch protection |
| Branch protection | Blocked on real `CODEOWNERS` handles |
| Engagement directory enforcement | The convention is documented and git-ignored but not enforced; a `pfia engagement init <client>` command would create the tree and scope the cache |
| Cache and cassette encryption at rest | Both hold verbatim policy text in plaintext. Adopted policies are generally public records, which lowers but does not remove the concern |
| Two harnesses, two ground-truth formats | `scripts/bakeoff.py` (instrument conflicts, Core statuses) and `scripts/benchmark.py` (verdict per control, `unmapped_findings`). Converge on one format after the first benchmark |
| Template naming | Resolved in 0.21.0: the screen is "Investment Policy Review · Policy Screen" (`screen.html`); `hsam_screen.html` is kept only as `--template screen-0.19` |
| SharePoint / Teams deployment | Deferred item 13 |
