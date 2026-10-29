# Open decisions and known gaps

Status as of 2026-10-27, after the Salt Lake County run (`--state ut --counties 035 --seed 42`).
Each item says what the gap is, what it costs in practice, and the options. Items marked
**modelling** change the model's rules and need a decision before any code changes. The others
are plumbing. Behavioural changes already made are in
[`CHANGELOG_vs_jiang2024.md`](../CHANGELOG_vs_jiang2024.md).

## 1. Bug: `WP_PROBA` ignores `--seed`

`code/0-preprocess/prepare-commute-data/build_tract_workplace_json.py --seed N` calls
`np.random.seed(N)`, but `src/tools.py` `wp_proba()` builds a fresh, unseeded
`np.random.default_rng()` when no generator is passed. The per-tract workplace-size
probabilities in `us_tract_number_work.json` therefore change every time the file is rebuilt.

- Impact: the two-run determinism check passed because both runs read the same JSON. Rebuilding
  inputs from scratch gives a different population for the same seed.
- Test gap: `tests/test_commute_prep.py` checks `WP_CNT` only, not `WP_PROBA`.
- Fix: pass `np.random.default_rng(seed)` into `wp_proba` and test that two builds match.

## 2. Large-impact modelling decisions

| Gap | Salt Lake run | Options |
|---|---|---|
| **Out-of-state jobs** (**modelling**) | 1.4% of jobs (1.9% statewide, 28,074 jobs). Those workers get no workplace. | Keep the paper's scope, or read every other state's LODES `aux` file for Utah homes and build `WP_CNT` for those destination tracts. |
| **Daycare participation** (**modelling**) | 64,059 children placed at full centres. Every child aged 0–4 is assumed to attend, and only about 13,700 places are nearby. | Keep it, model an attendance share, or send overflow to the nearest full centre instead of a random one. |
| **School data from 2015** | 16,425 children placed at full schools, in 20 fast-growing south-west valley tracts. | Add newer NCES CCD data (the `--source nces_ccd` option is a stub), or accept the gap. |

## 3. Smaller modelling decisions

### Education sites (`src/assign_education_site.py`, `prepare-edu/build_edu_sites.py`)

- When every site in the 11 km pool is full, a site in that pool is overfilled. The search does
  not widen to 100 km, and the overfilled site is picked uniformly at random.
- Sites with missing or negative enrollment get capacity 0, so they are used only as overflow.
  The alternatives are dropping them or estimating capacity from `POPULATION` or
  `FULL_TIME_TEACHERS`.
- Daycare capacity comes from `POPULATION`. The source layer does not say whether this is
  licensed capacity or actual enrollment.
- Included: public schools with NCES `STATUS` closed (2) or future (7) (25 and 24 Utah records),
  private schools, and schools with `Other`/`Unknown` level. `START_GRADE`/`END_GRADE` would give
  tighter age bands but changes the age rule.
- Only the state's own sites are used, so children near a state border can't attend
  across it.
- Schools and daycares have separate capacity counters. An `eduID` found in both tables is
  counted twice.

### Failed tracts

- Tract `49035980000` (16 people) is dropped. The leftover-person rule finds no household for 8
  adults, so they have no home point and `check_urban` fails. The original code fails the same
  way. The alternative is placing unhoused adults in an existing or new household.

### Inputs

- Urban areas file: `tl_2020_us_uac20.zip` is used. The corrected 2024 re-release
  (`tl_2020_us_uac20_corrected.zip`) and the 2010 version are the alternatives. The paper does
  not say which it used.
- Road cleaning removes duplicates within each `MTFCC` class. GRASS keeps the first feature
  across classes, which changes which edges count as S1200 workplace roads where classes overlap.
  `clean_road_network(class_column=None)` gives the GRASS behaviour.
- `rmsa` and vertex-to-segment snapping are not reproduced. The cleaned roads have not been
  compared with a GRASS run or the published OSF road file.

## 4. Engineering assumptions

### Blocks states other than Utah

- `EPSG:26912` (UTM 12N) is hard-coded for education buffers and home/work placement. Other
  states need their own projection, a per-state lookup, or a local equal-distance projection.
- Processed inputs mix coordinate systems: tract and urban `-work` files are EPSG:4326, while
  population points and roads are EPSG:4269. They should use one.

### Reproducibility

- All tracts share one random stream in GEOID order, so a `--counties` run doesn't produce
  the same people as those tracts in a full-state run with the same seed. Per-tract seeds from
  `(seed, GEOID)` would fix this.
- The age-sex shuffle in `__create_individuals__` follows `--seed` instead of the fixed 123.
  Passing `rng=None` restores the original.
- `src/assign_education_site.py` and `src/assign_household.py` still draw from Python's global
  `random`. They are reproducible through `seed_everything`, but not through an explicit
  generator. Converting them would change the random stream.

- `requirements.txt` pins no versions. The `.venv` rebuilt on 2026-10-27 got pandas 3.1,
  NumPy 2.5, NetworkX 3.7 and GeoPandas 1.2; the environment the Salt Lake runs used was lost in
  a temp-folder purge, so its versions are unknown. The same seed is only guaranteed to give the
  same output with the same library versions. A lock file (`pip freeze` into
  `requirements.lock`) would fix this.

### Quirks

- The synthesis driver reads only `<STATE>_road_cleaned.shp.zip`, so county road files
  (`<STATE>_c<counties>_road_cleaned.shp.zip`) are never used.
- `run-synthesis-by-state.py` logs tract errors with `exc_info=True`, which loguru ignores, so
  error logs have no traceback. `logger.opt(exception=e)` would record it.
- `load_clean_population_data` (used by `validation_tract_avg_hhold.py`) can rewrite the
  population GeoPackage in place.
- `src/external_validation.py::get_cosine_similarity` writes `cos_sim_fig.eps` to the current
  directory.
- Jiang et al.'s released `.pickle` populations can't be read. If they are needed, add an
  explicit converter for trusted files.
- Without `CENSUS_API_KEY`, the DP1 download uses data.census.gov's undocumented table endpoint.
- `__create_work_location__` takes `Point(x.coords[0])` of each clipped road and raises
  `IndexError` on an empty clip. This does not happen with raw TIGER coordinates, but any step
  that perturbs coordinates (such as a CRS round trip) triggers it.

## Resolved

- GEOIDs losing their leading zero for states 01–09 (`load_tract_id_work`, OD reads).
- `wNotFound` workers joining the daycare network (`wp_kind` in `src/create_social_networks.py`).
- `combine_in_out_county_data` reading a cwd-relative path.
- Validation scripts reading only `<state>_population.*`.

## Suggested order

1. Before the full Utah run: fix §1 (`WP_PROBA` seed) and the loguru traceback (plumbing).
2. Decide the §2 items. They don't block a run but change results.
3. Before any other state: the projection and coordinate-system items in §4.
