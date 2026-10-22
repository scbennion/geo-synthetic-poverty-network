# Changes vs. Jiang et al. (2024)

One line per behavioural change: file, function, what changed, why, effect on outputs.

## Task 0: packaging and single-geography switch

- `pyproject.toml`, `src/__init__.py`: new; make `-e .` in `requirements.txt` installable so `src` imports without `PYTHONPATH`. No effect on outputs.
- `src/settings.py`: data paths now come from a single `DATA_DIR` (env `GSPN_DATA_DIR`, default `<repo>/data`) and `RESULTS_DIR` is added; previously these were cwd-relative strings and the drivers hard-coded `../../data/...`. Same directory as before when run from the documented locations; no effect on outputs.
- `code/1-population-synthesis/run-synthesis-by-state.py` `__main__`: new `--state`, `--counties`, `--dry-run`; paths from settings; `us_tract_number_work.json` is now loaded inside `__main__` (skipped in dry-run) instead of at import. Default (no options) still runs all 51 areas with unchanged output names. With `--counties` only those tracts are synthesized and outputs are named `<state>/<state>_c<counties>_*` (e.g. `ut/ut_c035_population.gpkg`) so they never overwrite a full-state run.
- `code/2-social-networks/create_edu_hhold_get_work_pop.py` `create_by_state`: new `--state`/`--counties`; reads `<state>_c<counties>_population.pickle`, or filters the full-state file by the home-tract prefix of person `id` if no county run exists; networks written as `<state>/social_networks/<run>_*_network.csv` and the work population as `1-us/<run>_work_population.csv` (`us_` only for the all-states default). Paths from settings.
- `code/2-social-networks/create_work_networks.py` `create_us_work_network`: new `--state`/`--counties`; reads and writes `1-us/<run>_work_population.csv` / `<run>_work_network.csv` (`us_` only for the all-states default). Paths from settings.
- `code/3-validation/*.py`: hard-coded `../../data/...` and cwd-relative `data/...` paths replaced with settings paths. `validation_external_*.py` now find the `RESULTS_DIR` they import. No effect on outputs.
- `src/create_social_networks.py` `create_networks_types`: optional `name` for the network file prefix; defaults to the state abbreviation, so existing callers are unchanged.

## Open decisions

- Validation scripts still read `<state>_population.*` only; teaching them the `_c<counties>` names belongs with Agent B's `--state` work.

## Agent A: reproducibility

- `src/seeding.py`: new; `seed_everything(seed)` seeds Python `random` and returns `np.random.default_rng(seed)`; `add_seed_arg` adds `--seed` (default 42, the old hard-coded `r_seed`). No effect on outputs by itself.
- `code/1-population-synthesis/run-synthesis-by-state.py` `__main__`/`__synthesize__`: new `--seed`; one Generator is created per run and passed to every drawing step (previously only `random.seed(42)`, NumPy and pandas draws were unseeded). Same seed now gives byte-identical outputs; outputs at seed 42 differ from earlier runs because the NumPy random stream changed.
- `code/1-population-synthesis/run-synthesis-by-state.py` `__main__`: sets `OGR_CURRENT_DATE=2000-01-01T00:00:00Z` unless already set, so GDAL writes a fixed timestamp into `*_population.gpkg`/`*_workplace.gpkg` metadata instead of the wall-clock time; otherwise same-seed GeoPackages differ byte-wise. Only the GeoPackage `last_change` metadata changes.
- `src/ctreate_individuals.py` `__create_individuals__`: new `rng`; the age-sex shuffle uses it instead of the fixed `random_state=123` (kept when `rng` is None). Person-id-to-age assignment now depends on `--seed`.
- `src/assign_household.py` `__assign_household_order__`, `__find_members__`, `__htype_find_members__`, `__assign_left_pop_hhold__`: new `rng`; child/friend-count draws (`normal(2)`, `normal(1.6)`, `normal(1.5)`) and leftover-person household choice use `rng.normal`/`rng.choice` instead of `np.random.*`. Same distributions and rules; different random stream. Python `random.choice/sample` draws are unchanged (seeded by `seed_everything`).
- `src/create_space.py` `__create_home_location__`, `__create_work_location__`: new `rng`, passed as `random_state` to the point `.sample()` calls (previously global NumPy state). Placement rules unchanged.
- `src/assign_workplace.py` `__assign_workplaces__`, `generate_workplace_id`: new `rng`; worker/destination `.sample()` and workplace-index `choice` use it instead of global NumPy state. Rules unchanged.
- `src/tools.py` `wp_proba`: new optional `rng` (default: fresh unseeded `np.random.default_rng()`), so the workplace-size preprocessing can be seeded. Lognormal(mean=2) unchanged.
- `src/create_social_networks.py` `create_edges`, `create_network`, `create_networks_types`: new `seed`; each network call builds `np.random.default_rng(seed)` and passes it as `seed=` to `newman_watts_strogatz_graph(n, 4, 0.3)`. Previously unseeded. Each network file depends only on its input population and the seed, not on which other networks were already cached.
- `code/2-social-networks/create_edu_hhold_get_work_pop.py`, `create_work_networks.py`: new `--seed` (default 42) passed to the network builders.
- `tests/test_reproducibility.py`: synthetic 3-tract Salt Lake fixture runs synthesis plus both network drivers; same seed gives byte-identical files, a different seed gives different population, workplace, household and work-network files.

### Open decisions (Agent A)

- All tracts share one random stream in GEOID order, so a `--counties` run does not reproduce the same tracts' people from a full-state run with the same seed. Per-tract substreams (for example, seeding from `(seed, GEOID)`) would fix this. Not done because it goes beyond the single-seed spec.
- `__create_individuals__` now follows `--seed` instead of the fixed 123. To keep the original shuffle, pass `rng=None` there.
- `src/assign_education_site.py` `__find_edu_ID__` and `src/assign_household.py` still draw from Python's global `random`. They are reproducible through `seed_everything`, but not through an explicit generator. Converting them to `rng` would change the random stream again.

## Agent C: workplace counts

- `src/preprocess_data.py` `get_number_of_wp`: `J_c` is now the job total of the tract's own county (first 5 digits of the 11-digit GEOID) instead of `county_job_df.S000[0]`, the first county in the grouped table. Why: the documented rule is `floor(ESTAB_c * J_t / J_c)`; the old code divided by one arbitrary county's jobs for every tract in the state. Effect: `WP_CNT` changes for every tract outside the first county of each state; per-county `WP_CNT` sums now never exceed that county's `ESTAB`.
- `src/preprocess_data.py` `get_number_of_wp`: GEOIDs and CBP `county` codes are zero-padded (11 and 5 digits) before matching, replacing the 4-digit county branch for states 01–09. Why: `add_tract_workplaces.py` reads `county` back as an int (`1001`), and the OD `work` column for states 01–09 has 10 characters, so the old 5-digit comparison could miss and the 4-digit branch depended on lost zeros. Effect: states 01–09 match their own CBP county. The `state_code` argument is kept but no longer used. Rounding (`int()` truncation, i.e. floor) and the zero-and-log handling of failing tracts are unchanged.
- `src/preprocess_data.py`: new helpers `tract_geoid`, `county_fips`, `tract_and_county_jobs`; `get_number_of_wp` gains an optional `jobs=` so the OD table is grouped once rather than once per tract. Output is the same with or without it.
- `code/0-preprocess/prepare-commute-data/build_tract_workplace_json.py`: new driver writing `PROCESSED_DATA_DIR/us_tract_number_work.json` (JSON lines; `GEOID`, `WP_CNT`, `WP_PROBA`) from `get_number_of_wp` and `src.tools.wp_proba`. Scope: `--state` (default `ut`), optionally `--counties`, plus out-of-state work tracts in `RAW_DATA_DIR/work_commute/<st>_od_aux_JT00_2020.csv.gz`. `J_t`/`J_c` always come from the full OD of the tract's own state (`INTERIM_DATA_DIR/od/<st>-tract-od-2020.csv`). Tracts that fail (no OD jobs, no CBP row, or no OD file for their state) get `WP_CNT=0` and `WP_PROBA=[]`, and are listed in `PROCESSED_DATA_DIR/workplaces_error/<run>-tract-number-work-error.csv`. `--seed` optionally seeds `numpy.random` for `WP_PROBA`; by default it is unseeded, as before. Each run overwrites the single output file, so the JSON covers one state's scope rather than the whole country.

### Open decisions (Agent C)

- Out-of-state destinations: by the LODES spec the `aux` file holds jobs *located in* the state with residence outside it, so its `w_geocode`s are in-state and the "out-of-state destinations in the aux file" set is normally empty. Utah residents' out-of-state jobs appear in the neighbouring states' `aux` files (`h_geocode` in Utah), and the Utah OD table built by `combine_in_out_county_data` never lists those destinations. Decide whether the scope should be "work tracts in other states' aux files whose `h_geocode` is in-state", which needs those states' OD/aux files.
- `run-synthesis-by-state.py` `load_tract_id_work` reads the JSON with `pd.read_json` default dtype inference and then `.astype(str)`, which strips the leading zero from GEOIDs in states 01–09 (`"01001020100"` → `"1001020100"`). Utah GEOIDs are unaffected, but AZ (04) and CO (08) destination tracts would turn into `wNotFound`. Needs `dtype={'GEOID': str}` there (not changed here: outside Agent C's files).
- `WP_PROBA` uses the global `numpy.random` inside `src.tools.wp_proba`; after Agent A's rng refactor this driver should pass the run's `Generator` instead of `--seed`.
- `combine_in_out_county_data` (which produces the OD input) still globs the cwd-relative `data/raw-data/work_commute/...` instead of `RAW_DATA_DIR`. Not changed here.

## Agent D: education capacity

- `src/assign_education_site.py` `__find_edu_ID__`: the chosen site's enrollment counter is now incremented on every assignment (it never was, so `count < ENROLLMENT` was always tested against the supplied starting `count`). Why: the original code did not track remaining places, so schools and daycares could overfill without limit. Effect: children spill over to the next-nearest site in the candidate pool once the nearest one is full, so `wp` for school/daycare children changes and per-site totals stay at or below `ENROLLMENT`.
- `src/assign_education_site.py` `__find_edu_ID__`: the over-capacity fallback (`random.choice` among candidates, RNG unchanged) now runs only when every candidate is full, and each such pick is logged with loguru at WARNING (tract, child age, chosen `eduID`) and recorded in `EducationSites.fallbacks`. Why: make overfill visible and limit it to cases where it can't be avoided. Effect: a site goes over `ENROLLMENT` only through a logged fallback.
- `src/assign_education_site.py` new `EducationSites`: holds one site table indexed by `eduID`, its projected geometry and a running `{eduID: count}` counter that starts from the supplied `count` column. `__assign_education_site__` accepts it in place of the GeoDataFrame (a plain GeoDataFrame still works but gets a fresh counter on each call). Why: the counter must last across all tracts of a state run. No effect on outputs by itself.
- `code/1-population-synthesis/run-synthesis-by-state.py` `__main__`/`__synthesize__`: builds one `EducationSites` each for schools and daycares per state and passes them to every tract. If a tract fails, its school/daycare places are given back (`snapshot`/`restore`), because the failed tract's people are dropped. Logs the fallback totals per state. Effect: capacity is shared across the tracts of a state, in `GEOID` order (the `progress_apply` order), so tracts processed earlier get the nearer sites first.
- `src/assign_education_site.py` `tract_buffers` / `__assign_eduID__`: the tract search buffers are now built in metres after projecting to `PROJECTED_CRS = EPSG:26912` (NAD83 / UTM 12N, Utah-specific constant), with `NEAR_BUFFER_M = 11_000` and `FAR_BUFFER_M = 100_000` replacing `0.1` and `0.9` degrees. Site geometries are projected the same way (inputs assumed to be `GEOGRAPHIC_CRS = EPSG:4269` if they carry no CRS). Why: degree buffers are not real distances. Effect: north-south reach is about the same; east-west reach grows from about 8.4 km / 76 km (degrees of longitude at 40.7°N) to 11 km / 100 km, so somewhat more sites fall in the near pool. Age-band rules, the daycare no-age-filter rule, the near-then-far search order and distance ranking (`new_distance` on `LATITUDE`/`LONGITUDE`) are unchanged.
- `src/assign_education_site.py` `__find_edu_ID__`: an empty candidate pool now raises `ValueError` naming the tract and age, where before `random.choice` raised `IndexError`. The tract still fails and is logged by the driver as before.
- `src/assign_education_site.py`: the search buffers are built once per tract and the site table is indexed once per run, where before both were rebuilt for every child. Faster; no effect on outputs.

### Open decisions (Agent D)

- When every site in the 11 km pool is full, the code falls back to an over-capacity site in that pool. It does not widen the search to 100 km. Widening would change the buffer search, which this task leaves alone. A human should decide whether full near sites should trigger the far search.
- Fallback is a uniform `random.choice` among full candidates (left for Agent A's RNG work). Picking the nearest or least-overfilled site would be a modelling choice.
- `EPSG:26912` is right only for Utah. Multi-state runs need a per-state projected CRS (it is a parameter of `EducationSites`/`tract_buffers`). It could also move to `src/settings.py` alongside Agent E's road projection.
- Sites with missing `ENROLLMENT` never count as having room (same as before), so every assignment to them goes through the logged fallback.
- Schools and daycares have separate counters; if an `eduID` appears in both tables, its two counts are not combined.

## Agent G: education inputs

- `code/0-preprocess/prepare-edu/build_edu_sites.py` (new): builds `processed-data/edu/<state>_school_id.gpkg` and `<state>_daycare_id.gpkg` (default `--state ut`) from the EPA/ORNL "Educational Institutions, US, 2015, ORNL, SEGS" FileGDB (`https://edg.epa.gov/data/Public/OEI/ORNL_Education/ORNL_Education.zip`, read from `raw-data/edu/epa2015/`; `--download` fetches it with TLS verification on). The authors' preparation script was not published, so these files use the paper's cited source but are not guaranteed to match the authors' exact files.
- Same driver, layer mapping: schools = `PublicSchools` + `PrivateSchools` (filtered on `STATE`); daycare = `DayCareCenters`; `CollegesUniversities`/`SupplementalColleges` not used (school assignment covers ages 5-17). All records kept regardless of NCES `STATUS` (closed/future schools included). See open decisions.
- Same driver, ages: school `s_age`/`e_age` from the existing `src/preprocess_data.py` `__school_start_age__`/`__school_end_age__` on `LEVEL` (helpers unchanged); daycare rows get `s_age=0`, `e_age=4` (paper Step 2), which the assignment module does not read.
- Same driver, `ENROLLMENT`: schools use the source `ENROLLMENT`; daycare has no such field and uses `POPULATION`. Null or negative NCES codes (-1, -2, -9) become 0 (original value kept in `ENROLLMENT_SRC`, flagged `ENR_MISSING`), so those sites only receive children through the over-capacity fallback. Utah: 74 of 1,218 schools affected, 0 of 268 daycares.
- Same driver, IDs and geometry: `eduID` = `<state FIPS>s<5-digit n>` (schools) / `<state FIPS>d<n>` (daycare), numbered after sorting by layer and source ID, because `src/create_social_networks.py` selects school/daycare/work members with `wp.str.contains('s'/'d'/'w')`; `count` = 0; output reprojected from EPSG:4326 to EPSG:4269 (the tract CRS) and `LATITUDE`/`LONGITUDE` re-taken from the output geometry. The authors' original ID scheme is unknown.
- Same driver, `--source nces_ccd`: stub that raises `NotImplementedError`; placeholder for a later USBE/NCES CCD replacement.
- `tests/test_edu_sites.py` (new): synthetic zipped-FileGDB fixtures, no network. No effect on outputs.

### Open decisions (Agent G)

- Missing/negative enrollment set to 0 (site kept, used only as fallback) vs dropping those sites or imputing from `POPULATION`/`FULL_TIME_TEACHERS`.
- Daycare capacity from `POPULATION` (the only size field in `DayCareCenters`); the layer does not say whether it is licensed capacity or enrollment.
- Whether to drop public schools with NCES `STATUS` closed (2) or future (7) (Utah: 25 and 24 records), and whether to include private schools and `Other`/`Unknown` LEVEL schools (mapped to 5-17 by the existing helper). `START_GRADE`/`END_GRADE` would give tighter bands, but that changes the age rule.
- Sites are limited to the state's own records, so children near state borders cannot be assigned an out-of-state site.
