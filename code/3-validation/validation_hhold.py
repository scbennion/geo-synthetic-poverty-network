import argparse
import os
import pandas as pd
import geopandas as gpd

from tqdm import tqdm

from loguru import logger
from src.settings import PROCESSED_DATA_DIR, RESULTS_DIR, state_codes, state_dict
from src.verification import get_hholde_type_amount, plot_hhold_df
from src.after_validation_functions import read_error_tracts, read_run_census
from src.cli import add_geography_args, resolve_geography, run_name, us_run_name
from src.population_io import population_source, read_population

import warnings
# Ignore all warnings
warnings.filterwarnings("ignore")
warnings.filterwarnings("ignore", message="findfont: Font family")

def get_state_us_ver_hhold_dfs_plots(run_state_codes=state_codes, counties=None):
    census_path = os.path.join(PROCESSED_DATA_DIR, 'census')
    results_path = RESULTS_DIR

    final_hhold_ver_df = pd.DataFrame()  # hhold vali

    for state_code in tqdm(run_state_codes):
    #for state_code in tqdm(state_codes[7:9]):
        state_abbreviation = state_dict[state_code].lower()
        logger.info(f"========{state_abbreviation}========")
        name = run_name(state_abbreviation, counties)

        # hhold ver path- resulting
        state_hhold_ver_df_final_path = os.path.join(results_path,
                                                     f"{state_abbreviation}/{name}_hhold_verification.csv")
        plot_hhold_final_path = os.path.join(results_path,
                                             f"{state_abbreviation}/{name}_hhold_ver_plot.png")

        #read in path
        state_census_path = os.path.join(census_path, f"{state_abbreviation}-tracts-demo-work.shp.zip")
        # <run>_population.gpkg, or the full-state file for a county run that was not synthesized separately
        state_population_path, source_name = population_source(results_path, state_code, counties)
        state_error_tract_path = os.path.join(results_path,
                                              f"{state_abbreviation}/{source_name}_error_log.csv")

        try:
            error_tract_id = read_error_tracts(state_error_tract_path, state_abbreviation)

            if os.path.exists(state_census_path):
                state_census_gdf = read_run_census(state_census_path, state_code, counties)
                logger.info(f"Loaded census data - Count before removing errors: {len(state_census_gdf)}")

                good_state_census_gdf = state_census_gdf[~state_census_gdf['GEOID'].isin(error_tract_id)]
                logger.info(f"Count after removing errors: {len(good_state_census_gdf)}")
            else:
                logger.warning(f"Census data file not found: {state_census_path}")
                continue

            if os.path.exists(state_population_path):
                state_population_gdf = read_population(state_population_path, state_code=state_code, counties=counties)
            else:
                logger.warning(f"Population data file not found: {state_population_path}")
                continue

            #hhold
            state_hhold_ver_df = get_hholde_type_amount(state_census_gdf, good_state_census_gdf, state_population_gdf)
            state_hhold_ver_df.to_csv(state_hhold_ver_df_final_path)

            # plot
            plot_hhold_df(state_hhold_ver_df, plot_hhold_final_path)

            # concat all
            final_hhold_ver_df = pd.concat([final_hhold_ver_df, state_hhold_ver_df], axis=0)

        except Exception as e:
            (logger.error(f"An error occurred while processing {state_abbreviation}: {str(e)}"))

    if not os.path.exists(f"{results_path}/1-us/"):
        logger.info("Create U.S. path")
        os.makedirs(f"{results_path}/1-us/")

    us_name = us_run_name(run_state_codes, counties)
    us_hhold_ver_df_path = os.path.join(results_path, f"1-us/{us_name}_hhold_ver_df.csv")
    us_hhold_ver_plot_path = os.path.join(results_path, f"1-us/{us_name}_hhold_ver_plot.png")

    final_hhold_ver_df = final_hhold_ver_df.reset_index().rename(columns={'index': 'Type'})
    us_hhold_by_type = final_hhold_ver_df.groupby('Type').sum().reset_index()
    us_hhold_by_type.to_csv(us_hhold_ver_df_path)
    logger.info("Saved U.S. hhold verification DataFrtame results!!!")

    plot_hhold_df(us_hhold_by_type, us_hhold_ver_plot_path)
    logger.info("Saved U.S. hhold verification Plot!!!")

if __name__ == '__main__':
    parser = add_geography_args(argparse.ArgumentParser(description='Validate synthetic household types against the census'))
    args = parser.parse_args()
    try:
        run_state_codes, counties = resolve_geography(args)
    except argparse.ArgumentTypeError as e:
        parser.error(str(e))
    logger.info("Starting verification state")
    get_state_us_ver_hhold_dfs_plots(run_state_codes, counties)
    logger.info("Done!!!")

