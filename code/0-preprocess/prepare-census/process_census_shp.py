"""Join 2020 DP1 counts to TIGER tracts and prepare the urban-area file for one state.

    python code/0-preprocess/prepare-census/download_census_inputs.py --state ut
    python code/0-preprocess/prepare-census/process_census_shp.py --state ut

Writes (DATA_DIR from env GSPN_DATA_DIR, see src/settings.py):
    interim-data/census/ut_census_demo.shp.zip        tracts + DP1, EPSG:4269
    interim-data/census/ut_census_demo_4326.shp.zip   same, EPSG:4326 (read by add_tract_workplaces.py)
    processed-data/urban/UT_urban.gpkg                2020 urban areas touching the state
    processed-data/census/ut-tracts-demo-work.shp.zip tracts + DP1 + WP_CNT, only if
        interim-data/od/ut-tract-od-2020.csv and interim-data/cbp/workplace_cbp.csv exist

Exits 3 if the -work file could not be written (unless --skip-work).
`--state all` keeps the original all-states behaviour (census_demo.shp.zip, no urban/work step).
"""
import argparse
import os
import sys

import geopandas as gpd
import pandas as pd
from loguru import logger

from src import census_prep as cp
from src.cli import resolve_state_codes
from src.settings import INTERIM_DATA_DIR, PROCESSED_DATA_DIR, RAW_DATA_DIR, state_codes, state_dict


def load_dp1(run_state_codes, raw_data_path=RAW_DATA_DIR):
    """Per-state DP1 CSVs if present, else the national data.census.gov download."""
    per_state = [cp.dp1_state_csv_path(c, raw_data_path) for c in run_state_codes]
    if all(os.path.exists(p) for p in per_state):
        return pd.concat([cp.read_dp1(p) for p in per_state], ignore_index=True)
    national = cp.dp1_national_csv_path(raw_data_path)
    if os.path.exists(national):
        return cp.read_dp1(national)
    raise FileNotFoundError(f"No DP1 input: expected {per_state[0]} (download_census_inputs.py) or {national}")


def load_tract_boundaries(run_state_codes, raw_data_path=RAW_DATA_DIR, interim_data_path=INTERIM_DATA_DIR):
    """Per-state TIGER zips if present, else interim all_census.shp.zip (download_census_shp.py)."""
    per_state = [cp.tiger_tract_zip_path(c, raw_data_path) for c in run_state_codes]
    if all(os.path.exists(p) for p in per_state):
        return pd.concat([gpd.read_file(p) for p in per_state], ignore_index=True)
    national = cp.national_tract_path(interim_data_path)
    if os.path.exists(national):
        return gpd.read_file(national)
    raise FileNotFoundError(f"No tract boundaries: expected {per_state[0]} or {national}")


def process_state(state_code, demo_df, boundary, skip_work=False,
                  raw_data_path=RAW_DATA_DIR, interim_data_path=INTERIM_DATA_DIR,
                  processed_data_path=PROCESSED_DATA_DIR):
    """Returns True if every output, including the -work file, was written."""
    abbr = state_dict[state_code]
    state_census = cp.join_tracts_dp1(boundary, demo_df, [state_code])
    logger.info(f"{abbr}: {len(state_census)} tracts with DP1")
    cp.write_shp_zip(state_census, cp.census_demo_path(state_code, interim_data_path))
    state_census = state_census.to_crs(cp.TARGET_CRS)
    cp.write_shp_zip(state_census, cp.census_demo_path(state_code, interim_data_path, '_4326'))

    urban_zip = cp.urban_zip_path(raw_data_path)
    if os.path.exists(urban_zip):
        urban = cp.state_urban_areas(gpd.read_file(urban_zip), state_census)
        out = cp.urban_gpkg_path(state_code, processed_data_path)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        urban.to_file(out, driver='GPKG')
        logger.info(f"{abbr}: {len(urban)} urban areas saved to {out}")
        urban_ok = True
    else:
        logger.error(f"{abbr}: urban areas not written, {urban_zip} missing (download_census_inputs.py)")
        urban_ok = False

    if skip_work:
        return urban_ok
    od_file, cbp_file = cp.od_path(state_code, interim_data_path), cp.cbp_path(interim_data_path)
    missing = [p for p in (od_file, cbp_file) if not os.path.exists(p)]
    if missing:
        logger.error(f"{abbr}: {cp.tracts_demo_work_path(state_code, processed_data_path)} not written; "
                     f"WP_CNT needs commute inputs that are missing: {missing} "
                     f"(prepare-commute-data/process_lodes8.py, process_cbp.py)")
        return False
    od_df = pd.read_csv(od_file).reset_index(drop=True)
    work, error_tract = cp.add_workplace_counts(state_census, od_df, cp.read_cbp(cbp_file), state_code)
    cp.write_shp_zip(work, cp.tracts_demo_work_path(state_code, processed_data_path))
    error_dir = os.path.join(processed_data_path, 'workplaces_error')
    os.makedirs(error_dir, exist_ok=True)
    pd.DataFrame(error_tract, columns=['tract']).to_csv(
        os.path.join(error_dir, f"{abbr.lower()}-work-tract-error.csv"), index=False)
    return urban_ok


def process_all_states(raw_data_path=RAW_DATA_DIR, interim_data_path=INTERIM_DATA_DIR):
    """Original behaviour: every configured state into interim census/census_demo.shp.zip."""
    demo_df = load_dp1(state_codes, raw_data_path)
    boundary = gpd.read_file(cp.national_tract_path(interim_data_path))
    logger.info(f"Census Tracts Boundary Loaded: size is {len(boundary)}")
    census = cp.join_tracts_dp1(boundary, demo_df, state_codes)
    cp.write_shp_zip(census, os.path.join(interim_data_path, 'census', 'census_demo.shp.zip'))
    cp.write_shp_zip(census.to_crs(cp.TARGET_CRS),
                     os.path.join(interim_data_path, 'census', 'census_demo_4326.shp.zip'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--state', default='ut', help="state abbreviation or FIPS, or 'all' (default: ut)")
    parser.add_argument('--skip-work', action='store_true',
                        help='do not attempt the -work file (no commute inputs yet); exit 0')
    args = parser.parse_args(argv)

    if args.state.lower() == 'all':
        process_all_states()
        return 0
    try:
        run_state_codes = resolve_state_codes(args.state)
    except argparse.ArgumentTypeError as e:
        parser.error(str(e))

    demo_df = load_dp1(run_state_codes)
    boundary = load_tract_boundaries(run_state_codes)
    ok = all([process_state(code, demo_df, boundary, skip_work=args.skip_work) for code in run_state_codes])
    return 0 if ok else 3


if __name__ == '__main__':
    logger.info("Start...")
    status = main()
    logger.info("Done...")
    sys.exit(status)
