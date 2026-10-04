# Golden diff: Step 0 (provisional element audit, anti-pattern scoping)

Generated before re-blessing. Indices are the 0.18.0 numeric scores that Step 1 removes; they are shown only so the direction of each move is visible.

## Summary

| Case | Statutory before | after | Verdict/band flips | Score-only moves |
|---|---|---|---|---|
| city-deficient-deposits | 0.3556 | 0.3694 | 3 | 2 |
| city-detected-instruments | 0.2477 | 0.2576 | 3 | 2 |
| isd-corporate-bonds | 0.5812 | 0.6359 | 5 | 2 |
| tollway-enumerated-list | 0.5446 | 0.5494 | 4 | 1 |
| tollway-unindented | 0.5446 | 0.5494 | 4 | 1 |
| water-authority-conforming | 0.9 | 0.9442 | 6 | 0 |
| water-authority-pdf | 0.9 | 0.9442 | 6 | 0 |

## city-deficient-deposits

| | Before | After |
|---|---|---|
| Statutory index | 0.3556 | 0.3694 |
| Advisory index | 0.0881 | 0.18 |
| Mandatory-control failures | 7 | 7 |


| Control | Before | After | Cause |
|---|---|---|---|
| `TX-PFIA-2256.006-b-001` | CONFORMING (S) | CONFORMING (A) | reband |
| `TX-PFIA-2256.017-001` | DEFICIENT (S) | DEFICIENT (A) | reband, anti-pattern removed |
| `TX-PFIA-2256.026-001` | ABSENT (S) | ABSENT (A) | reband |

2 further control(s) changed score only.

## city-detected-instruments

| | Before | After |
|---|---|---|
| Statutory index | 0.2477 | 0.2576 |
| Advisory index | 0.0429 | 0.1806 |
| Mandatory-control failures | 5 | 5 |


| Control | Before | After | Cause |
|---|---|---|---|
| `TX-PFIA-2256.006-b-001` | CONFORMING (S) | CONFORMING (A) | reband |
| `TX-PFIA-2256.017-001` | DEFICIENT (S) | DEFICIENT (A) | reband, anti-pattern removed |
| `TX-PFIA-2256.026-001` | ABSENT (S) | ABSENT (A) | reband |

2 further control(s) changed score only.

## isd-corporate-bonds

| | Before | After |
|---|---|---|
| Statutory index | 0.5812 | 0.6359 |
| Advisory index | 0.3713 | 0.3868 |
| Mandatory-control failures | 4 | 3 |

Mandatory failures cleared: `TX-PFIA-2256.005-a-001`  

| Control | Before | After | Cause |
|---|---|---|---|
| `TX-PFIA-2256.005-a-001` | ABSENT (S) | CONFORMING (S) | element audit |
| `TX-PFIA-2256.006-b-001` | ABSENT (S) | ABSENT (A) | reband |
| `TX-PFIA-2256.008-a1-001` | DEFICIENT (A) | ABSENT (A) | element audit, anti-pattern removed |
| `TX-PFIA-2256.017-001` | CONFORMING (S) | CONFORMING (A) | reband, anti-pattern removed |
| `TX-PFIA-2256.026-001` | ABSENT (S) | ABSENT (A) | reband |

2 further control(s) changed score only.

## tollway-enumerated-list

| | Before | After |
|---|---|---|
| Statutory index | 0.5446 | 0.5494 |
| Advisory index | 0.6296 | 0.6129 |
| Mandatory-control failures | 4 | 4 |


| Control | Before | After | Cause |
|---|---|---|---|
| `TX-PFIA-2256.005-b-4-F-001` | ABSENT (S) | DEFICIENT (S) | element audit |
| `TX-PFIA-2256.006-b-001` | ABSENT (S) | ABSENT (A) | reband |
| `TX-PFIA-2256.017-001` | CONFORMING (S) | CONFORMING (A) | reband, anti-pattern removed |
| `TX-PFIA-2256.026-001` | DEFICIENT (S) | DEFICIENT (A) | reband |

1 further control(s) changed score only.

## tollway-unindented

| | Before | After |
|---|---|---|
| Statutory index | 0.5446 | 0.5494 |
| Advisory index | 0.6296 | 0.6129 |
| Mandatory-control failures | 4 | 4 |


| Control | Before | After | Cause |
|---|---|---|---|
| `TX-PFIA-2256.005-b-4-F-001` | ABSENT (S) | DEFICIENT (S) | element audit |
| `TX-PFIA-2256.006-b-001` | ABSENT (S) | ABSENT (A) | reband |
| `TX-PFIA-2256.017-001` | CONFORMING (S) | CONFORMING (A) | reband, anti-pattern removed |
| `TX-PFIA-2256.026-001` | DEFICIENT (S) | DEFICIENT (A) | reband |

1 further control(s) changed score only.

## water-authority-conforming

| | Before | After |
|---|---|---|
| Statutory index | 0.9 | 0.9442 |
| Advisory index | 0.7758 | 0.7571 |
| Mandatory-control failures | 2 | 1 |

Mandatory failures cleared: `TX-PFIA-2256.005-a-001`  

| Control | Before | After | Cause |
|---|---|---|---|
| `TX-PFIA-2256.005-a-001` | DEFICIENT (S) | CONFORMING (S) | element audit |
| `TX-PFIA-2256.006-b-001` | CONFORMING (S) | CONFORMING (A) | reband |
| `TX-PFIA-2256.017-001` | CONFORMING (S) | CONFORMING (A) | reband, anti-pattern removed |
| `TX-PFIA-2256.0208-001` | DEFICIENT (S) | CONFORMING (S) | element audit |
| `TX-PFIA-2256.023-b-001` | CONFORMING (A) | DEFICIENT (A) | element audit |
| `TX-PFIA-2256.026-001` | ABSENT (S) | ABSENT (A) | reband |

0 further control(s) changed score only.

## water-authority-pdf

| | Before | After |
|---|---|---|
| Statutory index | 0.9 | 0.9442 |
| Advisory index | 0.7758 | 0.7571 |
| Mandatory-control failures | 2 | 1 |

Mandatory failures cleared: `TX-PFIA-2256.005-a-001`  

| Control | Before | After | Cause |
|---|---|---|---|
| `TX-PFIA-2256.005-a-001` | DEFICIENT (S) | CONFORMING (S) | element audit |
| `TX-PFIA-2256.006-b-001` | CONFORMING (S) | CONFORMING (A) | reband |
| `TX-PFIA-2256.017-001` | CONFORMING (S) | CONFORMING (A) | reband, anti-pattern removed |
| `TX-PFIA-2256.0208-001` | DEFICIENT (S) | CONFORMING (S) | element audit |
| `TX-PFIA-2256.023-b-001` | CONFORMING (A) | DEFICIENT (A) | element audit |
| `TX-PFIA-2256.026-001` | ABSENT (S) | ABSENT (A) | reband |

0 further control(s) changed score only.


## Reading the flips

| Change | Cause | Assessment |
|---|---|---|
| 2256.006-b, 2256.017, 2256.026 move from statutory (S) to advisory (A) | Whole-control reband | Intended: adjudicative, permissive or recital provisions |
| 2256.005-a DEFICIENT/ABSENT → CONFORMING | Adoption date no longer scored; "in writing" dropped | Intended |
| 2256.008-a1 DEFICIENT → ABSENT (ISD) | "annually" removed; the fixture has no training text | Intended: the earlier DEFICIENT was a false positive |
| 2256.023-b CONFORMING → DEFICIENT (water authority) | "Prepared jointly" and "signed by each officer" split | Intended: the policy states one and not the other |
| 2256.0208 DEFICIENT → CONFORMING (water authority) | Split into bond proceeds / pledged revenue | **Stand-in extractor artifact.** The heuristic adapter treats any long word as a match signal and cannot judge support. Re-check under a recorded model run |
| 2256.005-b-4-F ABSENT → DEFICIENT (tollway) | Rewording adds common words the heuristic matches | **Stand-in extractor artifact**, as above |

The heuristic adapter pins plumbing, not review quality. The two artifact rows are expected
to resolve when goldens are blessed against a recorded model cassette (`--adapter replay`).
