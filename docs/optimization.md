# Optimization

Salt Lake County baseline: **121 minutes** (250 successful tracts, one failed).

| Step | Time before | Implemented optimization |
|---|---:|---|
| Household assignment | 85 min (71%) | Reuse household lists and probabilities; collect leftover assignments together. |
| Education assignment | 25 min (21%) | Find nearby eligible sites once per tract and age, then reuse the list. |
| Urban classification | 6 min (5%) | Check each home location once and share the result among residents. |

**Estimated rerun: about 70 minutes (60–80 minutes)**, saving roughly 50 minutes. This scales each stage's timing change for 79 completed tracts to the previous full run. The full rerun was stopped; this is an estimate.

Validation: identical assignments and random states on three real tracts; byte-identical output files for two synthetic runs. All 119 tests passed, with 28 focused checks passing again after readability cleanup.

Sources: [baseline timings](../data/results-data/ut/ut_c035_timing_summary.csv), [household code](../src/assign_household.py), [education code](../src/assign_education_site.py), [urban code](../src/tools.py). The baseline measures this project before optimization, not the upstream project.

## Estimated current breakdown

The 79-tract sample projects to about **68 minutes** for the full county:

| Step | Estimated time | Share |
|---|---:|---:|
| Household assignment | 52.5 min | 76.8% |
| Education assignment | 10.7 min | 15.6% |
| Job assignment | 2.6 min | 3.9% |
| Urban classification | 0.2 min | 0.3% |
| Everything else | 2.3 min | 3.4% |

These are estimates, not a completed full-run measurement. Values are rounded.

## Further improvements

- **Households first:** [member selection and assignment](../src/assign_household.py) still repeatedly filter the population table and write individual values. Measure these operations on 1–3 tracts, then consider array-based filtering and grouped writes, preserving candidate order and random draws.
- **Education second:** consider reusing [distance calculations](../src/assign_education_site.py) for children sharing a home and candidate sites. Keep capacity decisions sequential.

Halving household time would reduce the estimated total to about **42 minutes**. This illustrates the potential benefit; it is not a measured or promised speedup. These further improvements are not implemented.
