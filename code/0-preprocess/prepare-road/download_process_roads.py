"""Download TIGER/Line 2020 All Roads county files and combine them per state.

Writes ``INTERIM_DATA_DIR/road/<STATE>_road.shp.zip`` (or ``<STATE>_c<counties>_road.shp.zip``
with --counties). Next step: clean_roads.py.

    python code/0-preprocess/prepare-road/download_process_roads.py --state ut [--counties 035]
"""
import argparse

from loguru import logger

from src.cli import add_geography_args, resolve_geography, run_name
from src.preprocess_data import download_and_prepare_road_data
from src.settings import INTERIM_DATA_DIR, RAW_DATA_DIR, state_dict


def main(argv=None):
    parser = add_geography_args(argparse.ArgumentParser(description=__doc__.splitlines()[0]))
    parser.set_defaults(state='ut')
    args = parser.parse_args(argv)
    try:
        run_state_codes, counties = resolve_geography(args)
    except argparse.ArgumentTypeError as e:
        parser.error(str(e))

    for code in run_state_codes:
        state_abbreviation = state_dict[code]
        logger.info(f"Downloading {state_abbreviation}'s Road Network.")
        download_and_prepare_road_data(code, state_abbreviation,
                                       raw_data_path=RAW_DATA_DIR,
                                       interim_data_path=INTERIM_DATA_DIR,
                                       counties=counties,
                                       output_name=run_name(state_abbreviation, counties))
    logger.info("Finished!")


if __name__ == '__main__':
    main()
