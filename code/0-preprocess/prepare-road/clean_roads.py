"""Clean the combined road file and write the synthesis road input.

Pure-Python replacement for the former GRASS GIS script (clean_raod_with_grass.py):
snap vertices (10 m), split at crossings, drop duplicate geometries and label weakly
connected components; see src/clean_roads.py for the exact steps and differences.

Reads  INTERIM_DATA_DIR/road/<STATE>_road.shp.zip   (from download_process_roads.py)
Writes PROCESSED_DATA_DIR/road/<STATE>_road_cleaned.shp.zip
(``<STATE>_c<counties>_...`` with --counties; the synthesis driver reads the full-state name.)

    python code/0-preprocess/prepare-road/clean_roads.py --state ut [--counties 035] [--overwrite]
"""
import argparse
import timeit

from loguru import logger

from src.cli import add_geography_args, resolve_geography, run_name
from src.preprocess_data import process_interim_road_data
from src.settings import INTERIM_DATA_DIR, PROCESSED_DATA_DIR, state_dict


def main(argv=None):
    parser = add_geography_args(argparse.ArgumentParser(description=__doc__.splitlines()[0]))
    parser.set_defaults(state='ut')
    parser.add_argument('--overwrite', action='store_true', help='rebuild an existing output')
    args = parser.parse_args(argv)
    try:
        run_state_codes, counties = resolve_geography(args)
    except argparse.ArgumentTypeError as e:
        parser.error(str(e))

    for code in run_state_codes:
        state_abbreviation = state_dict[code]
        start = timeit.default_timer()
        logger.info(f"Cleaning {state_abbreviation}'s Road Network.")
        out = process_interim_road_data(state_abbreviation,
                                        interim_data_path=INTERIM_DATA_DIR,
                                        processed_data_path=PROCESSED_DATA_DIR,
                                        output_name=run_name(state_abbreviation, counties),
                                        overwrite=args.overwrite)
        logger.info(f"{out} done in {timeit.default_timer() - start:.1f} s")
    logger.info("All Done!")


if __name__ == '__main__':
    main()
