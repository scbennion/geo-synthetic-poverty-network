import argparse
import os
import re

import wget
import pandas as pd
import geopandas as gpd

from tqdm import tqdm
#from tqdm.notebook import tqdm

import timeit
import matplotlib.pyplot as plt
import numpy as np

from bs4 import BeautifulSoup
from loguru import logger
from src.settings import PROCESSED_DATA_DIR, RESULTS_DIR, state_codes, state_dict

from src.after_validation_functions import verifiy_avg_hhold_size, load_census_data, load_clean_population_data
from src.cli import add_geography_args, resolve_geography, in_counties, run_name, us_run_name
from src.population_io import population_source

import warnings

# Ignore all warnings
warnings.filterwarnings("ignore")
warnings.filterwarnings("ignore", message="findfont: Font family")

def check_restuling_exists(path):
    if os.path.exists(path):
        logger.info(f"Data File exists: {path}")
        return True
    else:
        return False

def get_state_avg_hhold_size_ver_dfs_plots(run_state_codes=state_codes, counties=None):
    census_path = os.path.join(PROCESSED_DATA_DIR, 'census')
    results_path = RESULTS_DIR

    final_avg_hhold_size_df = pd.DataFrame()

    for state_code in tqdm(run_state_codes):
        state_abbreviation = state_dict[state_code].lower()
        logger.info(f"========{state_abbreviation}========")
        name = run_name(state_abbreviation, counties)

        state_census_path = os.path.join(census_path, f"{state_abbreviation}-tracts-demo-work.shp.zip")
        # <run>_population.gpkg, or the full-state file for a county run that was not synthesized separately
        state_population_path, source_name = population_source(results_path, state_code, counties)
        state_error_tract_path = os.path.join(results_path, f"{state_abbreviation}/{source_name}_error_log.csv")

        state_tract_avg_hhold_final_path = os.path.join(results_path,
                                                        f"{state_abbreviation}/{name}_avg_hhold_verification.csv")
        state_plot_avg_hhold_final_path = os.path.join(results_path,
                                                       f"{state_abbreviation}/{name}_avg_hhold_plot.png")

        try:
            if check_restuling_exists(state_tract_avg_hhold_final_path) == True:
                logger.info(f"Data File exists: {state_tract_avg_hhold_final_path}")
                state_avg_hhold_size = pd.read_csv(state_tract_avg_hhold_final_path, dtype={'tract': str})
            else:  # load census
                state_census_gdf, good_state_census_gdf = load_census_data(state_census_path, state_error_tract_path,
                                                                           state_abbreviation, state_code, counties)
                # load population
                state_population_gdf = load_clean_population_data(state_population_path, state_abbreviation)
                if counties is not None:
                    state_population_gdf = state_population_gdf[
                        in_counties(state_population_gdf['id'], state_code, counties)]

                # verifiy avg hhold size function
                state_avg_hhold_size = verifiy_avg_hhold_size(state_census_gdf, good_state_census_gdf,
                                                              state_population_gdf)
                # save df
                state_avg_hhold_size.to_csv(state_tract_avg_hhold_final_path, index=False)

            # plot df and ave plot
        except Exception as e:
            (logger.error(f"An error occurred while processing {state_abbreviation}: {str(e)}"))
            continue

        final_avg_hhold_size_df = pd.concat([final_avg_hhold_size_df, state_avg_hhold_size], axis=0)

    # save final df
    if not os.path.exists(f"{results_path}/1-us/"):
        logger.info("Create U.S. path")
        os.makedirs(f"{results_path}/1-us/")

    us_avg_hhold_size_path = os.path.join(results_path, f"1-us/{us_run_name(run_state_codes, counties)}_avg_hhold_size_df.csv")
    final_avg_hhold_size_df.to_csv(us_avg_hhold_size_path, index=False)
    logger.info("Saved U.S. hhold verification DataFrtame results!!!")

if __name__ == '__main__':
    parser = add_geography_args(argparse.ArgumentParser(description='Validate tract average household size against the census'))
    args = parser.parse_args()
    try:
        run_state_codes, counties = resolve_geography(args)
    except argparse.ArgumentTypeError as e:
        parser.error(str(e))
    logger.info("Starting verification state")
    get_state_avg_hhold_size_ver_dfs_plots(run_state_codes, counties)
    logger.info("Done!!!")
