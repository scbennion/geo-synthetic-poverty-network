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
