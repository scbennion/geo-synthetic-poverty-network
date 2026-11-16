# Optimization

Salt Lake County baseline: **121 minutes** (250 successful tracts, one failed).

| Step | Time before | Implemented optimization |
|---|---:|---|
| Household assignment | 85 min (71%) | Select members using arrays; write memberships together; reuse leftover choices and probabilities. |
| Education assignment | 25 min (21%) | Reuse nearby-site lists and distance rankings for children sharing a home and eligible sites. |
| Urban classification | 6 min (5%) | Check each home location once and share the result among residents. |

**Latest estimated rerun: about 26 minutes; budget 25–40 minutes.** The first optimization pass projected about 68 minutes from 79 completed tracts. Scaling its household and education times by the latest three-tract speedups gives this new estimate. No full rerun was completed.

Validation: 48 focused tests passed, plus 220 comparisons with the previous member-selection code. Assignments and random states matched on three real tracts; both synthetic pipeline runs (seeds 42 and 7) produced byte-identical files compared with the previous code.

Sources: [baseline timings](../data-pre-reorganization/results-data/ut/ut_c035_timing_summary.csv), [household code](../pipeline/population_synthesis/assign_household.py), [education code](../pipeline/population_synthesis/assign_education_site.py), [urban code](../pipeline/population_synthesis/create_space.py). The baseline measures this project before optimization, not the upstream project.

## Estimated current breakdown

Latest projection for the full county:

| Step | Estimated time | Share |
|---|---:|---:|
| Household assignment | 13.7 min | 53.4% |
| Education assignment | 6.7 min | 26.2% |
| Job assignment | 2.6 min | 10.3% |
| Urban classification | 0.2 min | 0.9% |
| Everything else | 2.3 min | 9.1% |

These are estimates, not a completed full-run measurement. Values are rounded.

## Small performance test

Tracts near the 10th, 50th, and 90th population percentiles. Times below compare the first pass with the latest changes, without profiling overhead:

| Tract | People | Household before → after | Education before → after |
|---|---:|---:|---:|
| 49035113411 | 2,808 | 3.89 → 0.94 s | 1.34 → 0.82 s |
| 49035112916 | 4,736 | 8.62 → 2.20 s | 2.31 → 1.30 s |
| 49035111602 | 6,762 | 10.58 → 2.88 s | 2.08 → 1.48 s |

Combined speedups: **3.8× for households**, **1.6× for education**. Household comparisons used seed 7 (seed 42 also matched); education used seed 42. Capacity checks, fallback choices, and assignment order are unchanged.

The earlier profile found 68% of household time in member selection and 30% in repeated writes. Both operations are now optimized; those percentages describe the previous code.

## Further improvements

- Household selection remains the largest estimated cost; profile its new array filtering and index lookups before changing more code.
- Education is now about a quarter of estimated runtime; profile the remaining distance and capacity loops. Keep assignments sequential to preserve capacity decisions.

Further gains have not been measured. Use small tests and preserve exact same-seed results.
