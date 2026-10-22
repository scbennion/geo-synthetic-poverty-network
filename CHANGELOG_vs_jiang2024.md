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
