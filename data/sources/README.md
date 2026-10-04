# Statute snapshots

`verify_sources.py` checks every control's `source_text` against a vendored copy of the
canonical chapter. Snapshots live here as plain text or saved HTML, named for the
chapter and the retrieval date.

    GV.2256.txt          # current snapshot used by CI
    GV.2256.2026-09-05.txt   # dated archive

## Why vendored rather than fetched

`statutes.capitol.texas.gov` serves a client-rendered application. A plain HTTP GET
returns the shell, not the chapter, so an unattended fetch cannot be trusted to tell
you whether the law changed. Vendoring turns every amendment into a reviewable diff in
version control, which is the artifact an auditor wants, and keeps CI deterministic.

## Refreshing after a legislative session

1. Capture the chapter with a rendering fetch (headless browser, or the review tool's
   own fetch layer) from the `canonical_source` URL in each register.
2. Save to `GV.2256.<date>.txt` and update the `GV.2256.txt` symlink or copy.
3. Run `make verify` and fix every control the gate flags.
4. Bump `law_in_force_as_of` and `version` in each affected register.
5. Commit the snapshot diff, the control edits and the version bump together. The
   snapshot diff is the evidence for the control edits.
