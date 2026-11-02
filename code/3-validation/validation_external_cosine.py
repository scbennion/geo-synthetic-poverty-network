import argparse
import os

import pandas as pd
from tqdm import tqdm

from urllib3.exceptions import InsecureRequestWarning
import warnings
# Suppress only the InsecureRequestWarning
warnings.simplefilter('ignore', InsecureRequestWarning)

from loguru import logger
from src.settings import state_codes, state_dict, RAW_DATA_DIR, RESULTS_DIR
from src.external_validation import (read_pums_file,get_aggregate_spop_data,
                                     get_aggregate_pums20_data, read_clean_pums_tract_relationship,
                                     get_cosine_similarity)
from src.cli import add_geography_args, resolve_geography
from src.population_io import load_population

def get_us_aggregate_spop_data(pums_id_tract, run_state_codes=state_codes, counties=None):
    ### Prepare Spop each state
    us_agg_spop_data = pd.DataFrame()

    for state_code in tqdm(run_state_codes):
        #results_path = '../data/results-data'RESULTS_DIR
        results_path = RESULTS_DIR

        state_abbreviation = state_dict[state_code].lower()
        logger.info(f"========{state_abbreviation}========")

        # reads <run>_population.gpkg (county runs fall back to the full-state file, filtered)
        state_population, _ = load_population(results_path, state_code, counties, columns=['id', 'age', 'gender'])
        logger.info(f'Loaded {state_abbreviation} population-0 Size: {len(state_population)}')

        state_spop_agg_df = get_aggregate_spop_data(state_population, pums_id_tract)
        us_agg_spop_data = pd.concat([us_agg_spop_data, state_spop_agg_df], axis=0)
    #us_agg_spop_data.head()
    #save_us_agg_path = os.path.join(results_path, f"1-us/us_agg_spop.csv")
    #us_agg_spop_data.to_csv(save_us_agg_path)
    return us_agg_spop_data

def get_us_aggregate_pums_data(pums_path):
    pums_us = read_pums_file(pums_path)
    us_agg_pums_data = get_aggregate_pums20_data(pums_us)
    return us_agg_pums_data

if __name__ == '__main__':
    parser = add_geography_args(argparse.ArgumentParser(description='Cosine similarity of PUMA age/sex profiles, synthetic vs PUMS'))
    args = parser.parse_args()
    try:
        run_state_codes, counties = resolve_geography(args)
    except argparse.ArgumentTypeError as e:
        parser.error(str(e))
    logger.info('Start...')
    #PUMS and Census Tract Relationships
    pums_tract_path = os.path.join(RAW_DATA_DIR, 'puma/2020_Census_Tract_to_2020_PUMA.csv')
    pums_tract_relationship = read_clean_pums_tract_relationship(pums_tract_path)
    #Get Aggregated data from spop
    us_agg_spop_data = get_us_aggregate_spop_data(pums_tract_relationship, run_state_codes, counties)

    #Get Aggregated data from spop
    pums_data_path = os.path.join(RAW_DATA_DIR, 'puma/csv_pus_2022')
    us_agg_pums_data = get_us_aggregate_pums_data(pums_data_path)

    # compare the same PUMAs row by row (a --state/--counties run covers only some PUMAs)
    common_pumas = us_agg_spop_data.index.intersection(us_agg_pums_data.index)
    logger.info(f'PUMAs compared: {len(common_pumas)} '
                f'(synthetic {len(us_agg_spop_data)}, PUMS {len(us_agg_pums_data)})')

    #caculate cosine similarity
    A = us_agg_pums_data.loc[common_pumas].to_numpy()
    B = us_agg_spop_data.loc[common_pumas].to_numpy()
    get_cosine_similarity(A, B)

    logger.info("Done!!!")
