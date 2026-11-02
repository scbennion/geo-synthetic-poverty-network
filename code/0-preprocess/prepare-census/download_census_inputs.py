"""Download the census inputs process_census_shp.py needs for one state.

    python code/0-preprocess/prepare-census/download_census_inputs.py --state ut

Writes under RAW_DATA_DIR (DATA_DIR from env GSPN_DATA_DIR):
    demographic-profile-20/DECENNIALDP2020.DP1-ut-tracts.csv
        2020 Census Demographic Profile, table DP1, all tracts in the state.
        Source: Census API dataset 2020/dec/dp, group(DP1). Uses api.census.gov when
        CENSUS_API_KEY is set (the API rejects keyless requests), otherwise the
        data.census.gov table endpoint, which returns the same query without a key.
    census/tl_2020_49_tract.zip
        https://www2.census.gov/geo/tiger/TIGER2020/TRACT/
    urban/tl_2020_us_uac20.zip
        2020 urban areas, https://www2.census.gov/geo/tiger/TIGER2020/UAC/ (national file)

Existing TIGER/urban zips are reused; the DP1 CSV is re-fetched unless present.
TLS certificates are verified.
"""
import argparse
import os

from loguru import logger

from src import census_prep as cp
from src.cli import resolve_state_codes
from src.settings import RAW_DATA_DIR


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--state', default='ut', help='state abbreviation or FIPS (default: ut)')
    args = parser.parse_args(argv)
    try:
        run_state_codes = resolve_state_codes(args.state)
    except argparse.ArgumentTypeError as e:
        parser.error(str(e))

    for code in run_state_codes:
        dp1 = cp.dp1_state_csv_path(code, RAW_DATA_DIR)
        if os.path.exists(dp1):
            logger.info(f"DP1 already present: {dp1}")
        else:
            cp.download_dp1_tracts(code, RAW_DATA_DIR)
        logger.info(f"TIGER tracts: {cp.download_tiger_tracts(code, RAW_DATA_DIR)}")
    logger.info(f"Urban areas: {cp.download_urban_areas(RAW_DATA_DIR)}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
