"""County establishment counts (ESTAB) from 2020 County Business Patterns.

Reads the paper's CB2000CBP.zip (raw-data/workplace/CB2000CBP.zip, pipe-delimited, about
2.7 GB unzipped; streamed, not extracted) or a data.census.gov table CSV passed with
--input, and writes interim-data/cbp/workplace_cbp.csv with one row per county for all
industries, legal forms and establishment sizes. The output covers every county in the
input, so one run serves all states.

Run: python process_cbp.py [--download] [--input PATH]
"""
import argparse
import os

from loguru import logger
from src.preprocess_data import CBP_URL, download_file, read_cbp_counties
from src.settings import RAW_DATA_DIR, INTERIM_DATA_DIR

DEFAULT_INPUT = os.path.join(RAW_DATA_DIR, 'workplace', 'CB2000CBP.zip')
OUTPUT = os.path.join(INTERIM_DATA_DIR, 'cbp', 'workplace_cbp.csv')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--input', default=DEFAULT_INPUT,
                        help='CB2000CBP.zip / .dat, or a data.census.gov CBP2020.CB2000CBP-Data.csv')
    parser.add_argument('--download', action='store_true', help=f'download {CBP_URL} to the default input path')
    args = parser.parse_args(argv)

    if args.download and not os.path.exists(args.input):
        os.makedirs(os.path.dirname(args.input), exist_ok=True)
        logger.info(f"Downloading {CBP_URL} to {args.input}")
        if not download_file(CBP_URL, args.input):
            raise SystemExit(f"Failed to download {CBP_URL}")
    if not os.path.exists(args.input):
        raise SystemExit(f"CBP input not found: {args.input} (pass --download or --input)")

    logger.info(f"Reading CBP from {args.input}")
    campany_df = read_cbp_counties(args.input)
    logger.info(f"There are {len(campany_df)} counties, {campany_df['ESTAB'].sum()} establishments")

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    logger.info(f"Saving County Workplace df to {OUTPUT}")
    campany_df.to_csv(OUTPUT)


if __name__ == '__main__':
    main()
