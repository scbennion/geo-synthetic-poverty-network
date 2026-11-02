import argparse
import os
import pandas as pd
import geopandas as gpd
#import fiona
from tqdm import tqdm
import matplotlib.pyplot as plt

from src.bg_validate_functions import pop_to_geo_df, prepare_bg_spop_gdf
from src.settings import RAW_DATA_DIR, PROCESSED_DATA_DIR, RESULTS_DIR, state_codes, state_dict
from loguru import logger
from src.cli import add_geography_args, resolve_geography, in_counties, run_name, us_run_name
from src.population_io import load_population


def load_us_bg_boundary_pop():
    logger.info('Loading US BG data..')
    return gpd.read_file(os.path.join(PROCESSED_DATA_DIR, 'acs/acs_bg_boundary_population.gpkg'))

# Function to calculate Spearman correlation for each group
# def spearman_corr(group):
#     from scipy.stats import spearmanr
#     corr, _ = spearmanr(group['B01001e1'], group['count'])
#     return corr
# Function to calculate Spearman correlation for each group
def spearman_corr(group):
    from scipy.stats import spearmanr
    if group['B01001e1'].nunique() == 1 or group['count'].nunique() == 1:
        # Return NaN if any of the columns is constant (i.e., all values are identical)
        return float('nan')
    corr, _ = spearmanr(group['B01001e1'], group['count'])
    return corr
def get_spc_tract(us_bg_boundary_pop, run_state_codes=state_codes, counties=None):
    results = []
    for state_code in tqdm(run_state_codes):

        state_abbreviation = state_dict[state_code]
        name = run_name(state_abbreviation.lower(), counties)
        logger.info(f'Processing {state_abbreviation}...')
        # load spop: <run>_population.gpkg already holds the home points (EPSG:4269)
        logger.info(f'Loading {state_abbreviation} Population...')
        state_population, _ = load_population(RESULTS_DIR, state_code, counties,
                                              columns=['id', 'long', 'lat', 'geometry'])
        state_population_gdf = state_population.to_crs('EPSG:4269')

        #get bg population gdf from the us file using state code
        logger.info(f'Getting {state_abbreviation} BG Population...')
        state_bg_population = us_bg_boundary_pop[us_bg_boundary_pop['STATEFP'] == state_code]
        if counties is not None:
            # block-group GEOID20 starts with the 11-digit tract GEOID
            state_bg_population = state_bg_population[
                in_counties(state_bg_population['GEOID20'], state_code, counties)]

        #process bg and spop
        state_bg_vali_df = prepare_bg_spop_gdf(state_bg_population, state_population_gdf)

        # Group by 'tract' and calculate Spearman correlation
        state_spearman_corrs = state_bg_vali_df.groupby('tract').apply(spearman_corr, include_groups=False).reset_index()
        state_spearman_corrs.columns = ['tract', 'spearman_correlation']

        #save a csv for each state
        state_spc_save_path = os.path.join(RESULTS_DIR,
                                             f"{state_abbreviation.lower()}/{name}_spc_tract.csv")
        logger.info(f'Saving spc state {state_abbreviation} data to {state_spc_save_path}')
        state_spearman_corrs.to_csv(state_spc_save_path)

        #
        over_5_corr = len(state_spearman_corrs[state_spearman_corrs['spearman_correlation'] >= 0.5])
        over_5_ratio = len(state_spearman_corrs[state_spearman_corrs['spearman_correlation'] >= 0.5]) / len(state_spearman_corrs)

        results.append({
            'state_abv': state_abbreviation,
            'count': over_5_corr,
            'all' : len(state_spearman_corrs),
            'ratio': over_5_ratio
        })
    return pd.DataFrame(results)

if __name__ == '__main__':
    parser = add_geography_args(argparse.ArgumentParser(description='Spearman correlation of block-group counts, synthetic vs ACS'))
    args = parser.parse_args()
    try:
        run_state_codes, counties = resolve_geography(args)
    except argparse.ArgumentTypeError as e:
        parser.error(str(e))
    state_data_df = get_spc_tract(load_us_bg_boundary_pop(), run_state_codes, counties)
    logger.info(f"Data collected for states:\n{state_data_df}")
    #logger.info(f"Tracts with Spearman correlation >= 0.5: {tract_over5_count}")
    #logger.info(f"Ratio of tracts with Spearman correlation >= 0.5: {tract_over5_ratio:.2%}")
    save_path = os.path.join(RESULTS_DIR, f"1-us/{us_run_name(run_state_codes, counties)}_state_spearman_correlation.csv")
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    state_data_df.to_csv(save_path, index=False)
    logger.info(f"CSV saved as {save_path}")
