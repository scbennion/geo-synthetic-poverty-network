import argparse
import os
from pathlib import Path
import pandas as pd

from tqdm import tqdm
#from tqdm.notebook import tqdm

from loguru import logger
from src.settings import RESULTS_DIR, state_codes, state_dict
from src.cli import add_geography_args, resolve_geography, in_counties, run_name, us_run_name

from src.create_social_networks import create_networks_types
from src.seeding import DEFAULT_SEED, add_seed_arg

def create_by_state(run_state_codes=state_codes, counties=None, seed=DEFAULT_SEED):
    results_path = RESULTS_DIR

    work_population = pd.DataFrame()

    for state_code in tqdm(run_state_codes):
        state_abbreviation = state_dict[state_code].lower()
        logger.info(f"========{state_abbreviation}========")
        state_abbreviation = state_dict[state_code].lower()

        name = run_name(state_abbreviation, counties)
        state_population_path = os.path.join(results_path, f"{state_abbreviation}/{name}_population.pickle")
        if counties is not None and not Path(state_population_path).exists():
            # no county-run output; take these counties from the full-state run
            state_population_path = os.path.join(results_path, f"{state_abbreviation}/{state_abbreviation}_population.pickle")
            logger.info(f"No {name} population, filtering {state_population_path}")

        final_population_path = os.path.join(results_path, f"1-us/{us_run_name(run_state_codes, counties)}_work_population.csv")
        # todo check cache file
        state_population = pd.read_pickle(state_population_path).loc[:, ['id', 'age', 'hhold', 'wp']]
        if counties is not None:
            # person ids start with the home tract GEOID
            state_population = state_population[in_counties(state_population['id'], state_code, counties)]
        # Create Social Network (Edu and Household)
        create_networks_types(state_population, results_path, state_abbreviation, name, seed=seed)

        work_population = pd.concat([work_population,
                                     state_population[(state_population.age >= 18) &
                                                      (state_population.wp.str.contains("w"))]], axis=0
                                    )

    if not Path(final_population_path).exists():
        work_population.to_csv(final_population_path, index=False)
    else:
        logger.info("US work population already exists")

if __name__ == '__main__':
    parser = add_seed_arg(add_geography_args(argparse.ArgumentParser(description='Create education and household networks')))
    args = parser.parse_args()
    try:
        run_state_codes, counties = resolve_geography(args)
    except argparse.ArgumentTypeError as e:
        parser.error(str(e))
    logger.info("Starting Creating and Getting Work Population")
    create_by_state(run_state_codes, counties, args.seed)
    logger.info("Done!!!")