"""Add WP_CNT (workplaces per tract) to the DP1 tracts: processed-data/census/<st>-tracts-demo-work.shp.zip.

Inputs: interim-data/cbp/workplace_cbp.csv (process_cbp.py), interim-data/od/<st>-tract-od-2020.csv
(process_lodes8.py) and the tracts from prepare-census/process_census_shp.py: the per-state
interim-data/census/<st>_census_demo_4326.shp.zip if present, else the all-states
census_demo_4326.shp.zip. process_census_shp.py --state <st> runs this same step itself
when the commute inputs exist.
"""
import argparse
import os

import pandas as pd
import geopandas as gpd

from loguru import logger
from tqdm import tqdm
from src import census_prep as cp
from src.cli import resolve_state_codes
from src.settings import INTERIM_DATA_DIR, PROCESSED_DATA_DIR, state_dict


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', default=None, help="state abbreviation or FIPS; default: all states")
    args = parser.parse_args(argv)
    try:
        run_state_codes = resolve_state_codes(args.state)
    except argparse.ArgumentTypeError as e:
        parser.error(str(e))

    # 1 Read Data
    cbp_path = cp.cbp_path(INTERIM_DATA_DIR)
    logger.info(f"Reading county company data from {cbp_path}")
    cbp = cp.read_cbp(cbp_path)
    logger.info(cbp.head())

    national_census_path = os.path.join(INTERIM_DATA_DIR, "census/census_demo_4326.shp.zip")
    national_census = None

    for code in tqdm(run_state_codes):
        state_abbreviation = state_dict[code]
        logger.info(f" {state_abbreviation}'s Data.")

        full_census_path = cp.tracts_demo_work_path(code, PROCESSED_DATA_DIR)
        if os.path.exists(full_census_path):
            logger.info(f"{state_abbreviation} Census gdf with demo and work info data already exists.")
            continue

        state_census_path = cp.census_demo_path(code, INTERIM_DATA_DIR, '_4326')
        if os.path.exists(state_census_path):
            logger.info(f"Reading Census Tract data from {state_census_path}")
            state_census = gpd.read_file(state_census_path)
        else:
            if national_census is None:
                logger.info(f"Reading Census Tract data from {national_census_path}")
                national_census = gpd.read_file(national_census_path)
            state_census = national_census[national_census['STATEFP'] == code].copy()

        od_df = pd.read_csv(cp.od_path(code, INTERIM_DATA_DIR)).reset_index(drop=True)
        state_census, error_tract = cp.add_workplace_counts(state_census, od_df, cbp, code)

        logger.info(f"Saving census tract to {full_census_path}")
        cp.write_shp_zip(state_census, full_census_path)

        error_path = os.path.join(PROCESSED_DATA_DIR, "workplaces_error")
        os.makedirs(error_path, exist_ok=True)
        full_error_path = os.path.join(error_path, f"{state_abbreviation.lower()}-work-tract-error.csv")
        logger.info(f"Saving error tract to {full_error_path}")
        pd.DataFrame(error_tract, columns=['tract']).to_csv(full_error_path, index=False)

    logger.info("All Done!")


if __name__ == '__main__':
    main()
