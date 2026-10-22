import argparse
import os

import pandas as pd
import geopandas as gpd

from tqdm import tqdm
from loguru import logger

from src.settings import PROCESSED_DATA_DIR, RESULTS_DIR, state_codes, state_dict
from src.after_validation_functions import verifiy_age_group, plot_ver_age_df, read_error_tracts, read_run_census
from src.cli import add_geography_args, resolve_geography, run_name
from src.population_io import population_source, read_population

import warnings
# Ignore all warnings
warnings.filterwarnings("ignore")
warnings.filterwarnings("ignore", message="findfont: Font family")

def get_state_us_age_ver_dfs_plots(run_state_codes=state_codes, counties=None):
    census_path = os.path.join(PROCESSED_DATA_DIR, 'census')
    results_path = RESULTS_DIR

    final_age_ver_df = pd.DataFrame()

    for state_code in tqdm(run_state_codes):
        state_abbreviation = state_dict[state_code].lower()
        logger.info(f"========{state_abbreviation}========")
        name = run_name(state_abbreviation, counties)

        state_age_ver_df_final_path = os.path.join(results_path,
                                                   f"{state_abbreviation}/{name}_age_verification.csv")
        plot_final_path = os.path.join(results_path, f"{state_abbreviation}/{name}_age_ver_plot.png")

        state_census_path = os.path.join(census_path, f"{state_abbreviation}-tracts-demo-work.shp.zip")
        # <run>_population.gpkg, or the full-state file for a county run that was not synthesized separately
        state_population_path, source_name = population_source(results_path, state_code, counties)
        state_error_tract_path = os.path.join(results_path,
                                              f"{state_abbreviation}/{source_name}_error_log.csv")

        try:
            error_tract_id = read_error_tracts(state_error_tract_path, state_abbreviation)

            if os.path.exists(state_census_path):
                state_census_gdf = read_run_census(state_census_path, state_code, counties)#all census
                logger.info(f"Loaded census data - Count before removing errors: {len(state_census_gdf)}")
                good_state_census_gdf = state_census_gdf[~state_census_gdf['GEOID'].isin(error_tract_id)]#census remove error tracts
                logger.info(f"Count after removing errors: {len(good_state_census_gdf)}")
            else:
                logger.warning(f"Census data file not found: {state_census_path}")
                continue

            if os.path.exists(state_population_path):
                logger.info(f"Loading {state_abbreviation} population..")
                state_population_gdf = read_population(state_population_path, state_code=state_code, counties=counties)
                logger.info(f"Loaded Population data - Count before removing nans in 'id': {len(state_population_gdf)}")
                state_population_gdf = state_population_gdf.dropna(subset=['id'])
                logger.info(f"Count after removing nans in 'id': {len(state_population_gdf)}")
            else:
                logger.warning(f"Population data file not found: {state_population_path}")
                continue

            state_age_ver_df = verifiy_age_group(state_census_gdf, good_state_census_gdf, state_population_gdf)
            state_age_ver_df.to_csv(state_age_ver_df_final_path)

            plot_ver_age_df(state_age_ver_df, plot_final_path)

            final_age_ver_df = pd.concat([final_age_ver_df, state_age_ver_df], axis=0)

        except Exception as e:
            (logger.error(f"An error occurred while processing {state_abbreviation}: {str(e)}"))

if __name__ == '__main__':
    parser = add_geography_args(argparse.ArgumentParser(description='Validate synthetic age/sex counts against the census'))
    args = parser.parse_args()
    try:
        run_state_codes, counties = resolve_geography(args)
    except argparse.ArgumentTypeError as e:
        parser.error(str(e))
    logger.info("Starting verification state")
    get_state_us_age_ver_dfs_plots(run_state_codes, counties)
    logger.info("Done!!!")
