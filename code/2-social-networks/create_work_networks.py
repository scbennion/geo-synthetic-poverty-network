import argparse
import os
from pathlib import Path
import pandas as pd
from loguru import logger
from src.create_social_networks import create_network, to_csv
from src.settings import RESULTS_DIR, state_codes
from src.cli import add_geography_args, resolve_geography, us_run_name
from src.seeding import DEFAULT_SEED, add_seed_arg


def create_us_work_network(folder_path, run_state_codes=state_codes, counties=None, seed=DEFAULT_SEED):
    try:
        # Ensuring the directory exists
        output_dir = Path(folder_path) / "1-us"
        output_dir.mkdir(parents=True, exist_ok=True)
        name = us_run_name(run_state_codes, counties)
        work_nx_path = output_dir / f"{name}_work_network.csv"

        # Load population
        logger.info("Loading work population")
        population_path = output_dir / f"{name}_work_population.csv"
        population = pd.read_csv(population_path)

        if not work_nx_path.exists():
            logger.info("No Networks, Creating US Work network...")
            # Assuming create_network function exists and works as expected
            new_network = create_network(population.set_index('id'), "Work", seed)
            # Saving
            to_csv(new_network, population.set_index('id'), work_nx_path)
        else:
            logger.info('Work Network already exists')

    except Exception as e:
        logger.error(f"An error occurred: {e}")

if __name__ == '__main__':
    parser = add_seed_arg(add_geography_args(argparse.ArgumentParser(description='Create work network')))
    args = parser.parse_args()
    try:
        run_state_codes, counties = resolve_geography(args)
    except argparse.ArgumentTypeError as e:
        parser.error(str(e))
    logger.info("Creating US Work Network...")
    create_us_work_network(RESULTS_DIR, run_state_codes, counties, args.seed)
    logger.info("Done!")