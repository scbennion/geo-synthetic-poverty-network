"""Download 2020 LODES8 OD files and aggregate them to tract-to-tract job counts.

For each state: raw-data/work_commute/<st>_od_{main,aux}_JT00_2020.csv.gz (downloaded,
certificates verified) -> interim-data/od/<st>-tract-od-2020.csv (read by the workplace
counts) and processed-data/od/<st>-tract-od-2020.csv (read by the synthesis driver).

Run: python process_lodes8.py --state ut      ('all' for every state)
"""
import argparse

from loguru import logger
from tqdm import tqdm
from src.cli import resolve_state_codes
from src.preprocess_data import download_lodes_2020_data, combine_in_out_county_data
from src.settings import state_dict


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--state', default='ut', help="state abbreviation or FIPS, or 'all' (default: ut)")
    parser.add_argument('--skip-download', action='store_true', help='use the LODES files already in raw-data')
    args = parser.parse_args(argv)
    try:
        run_state_codes = resolve_state_codes(None if args.state.lower() == 'all' else args.state)
    except argparse.ArgumentTypeError as e:
        parser.error(str(e))

    for code in tqdm(run_state_codes):
        state_abbreviation = state_dict[code].lower()
        if not args.skip_download:
            logger.info(f"Downloading {state_abbreviation}'s LODES8.")
            download_lodes_2020_data(state_abbreviation)
        logger.info(f"Combining {state_abbreviation}'s in and out state.")
        combine_in_out_county_data(state_abbreviation, code)
    logger.info("Finished downloading and combining LODES8.")


if __name__ == "__main__":
    main()
