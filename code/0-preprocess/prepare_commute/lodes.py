"""Download LODES8 commuting data and aggregate block flows to tract pairs."""
import os

import pandas as pd
from loguru import logger

from _downloads import download_file
from src.settings import RAW_DATA_DIR, INTERIM_DATA_DIR, PROCESSED_DATA_DIR, state_dict

LODES_TYPES = ("main", "aux")
LODES_YEAR = 2020


def lodes_path(state_name, lodes_type, raw_data_dir=RAW_DATA_DIR, year=LODES_YEAR):
    """Path of a downloaded LODES8 OD file, e.g. raw-data/work_commute/ut_od_main_JT00_2020.csv.gz."""
    return os.path.join(raw_data_dir, "work_commute", f"{state_name.lower()}_od_{lodes_type}_JT00_{year}.csv.gz")


def download_lodes_2020_data(state_name, raw_data_dir=RAW_DATA_DIR):
    """
    Download the 2020 LODES8 `main` and `aux` OD files (JT00, all jobs) for a state.

    Cached files are kept. Certificates are verified; a failed download raises
    instead of being skipped, so a missing file is never mistaken for no commuters.
    """
    os.makedirs(os.path.join(raw_data_dir, "work_commute"), exist_ok=True)
    for lodes_type in LODES_TYPES:
        lodes_full_path = lodes_path(state_name, lodes_type, raw_data_dir)
        if os.path.exists(lodes_full_path):
            logger.info(f"Cached LODES data found at {lodes_full_path}. Skipping download.")
            continue
        url = f"https://lehd.ces.census.gov/data/lodes/LODES8/{state_name.lower()}/od/{os.path.basename(lodes_full_path)}"
        logger.info(f"Downloading {url} to {lodes_full_path}")
        if not download_file(url, lodes_full_path):
            raise RuntimeError(f"Failed to download LODES file {url}")
        logger.info(f"Saved LODES data to {lodes_full_path}")


def combine_in_out_county_data(state_ab, state_code, inter_data_dir=INTERIM_DATA_DIR,
                               raw_data_dir=RAW_DATA_DIR, processed_data_dir=PROCESSED_DATA_DIR):
    """
    Aggregate a state's 2020 LODES `main` + `aux` block OD files to tract pairs.

    Block geocodes are read as text and zero-padded to 15 digits, so the first 11
    digits are the tract GEOID for every state. Writes `work`, `home`, `S000` to
    interim-data/od/<st>-tract-od-2020.csv (input to the workplace counts) and the
    same file to processed-data/od/ (input to the synthesis driver). Returns the table.
    """
    frames = []
    for lodes_type in LODES_TYPES:
        path = lodes_path(state_ab, lodes_type, raw_data_dir)
        if not os.path.exists(path):
            raise FileNotFoundError(f"LODES file missing: {path} (run process_lodes8.py)")
        df = pd.read_csv(path, usecols=["w_geocode", "h_geocode", "S000"],
                         dtype={"w_geocode": str, "h_geocode": str})
        logger.info(f"Loaded file {path} with shape {df.shape}")
        frames.append(df)
    combine_df = pd.concat(frames, ignore_index=True)
    logger.info(f"combined with shape {combine_df.shape}")

    combine_df["work"] = combine_df.w_geocode.str.zfill(15).str[:11]
    combine_df["home"] = combine_df.h_geocode.str.zfill(15).str[:11]
    od_final = combine_df.groupby(["work", "home"], as_index=False)["S000"].sum()

    file_name = f"{state_ab.lower()}-tract-od-2020.csv"
    for out_dir in (inter_data_dir, processed_data_dir):
        output_path = os.path.join(out_dir, "od", file_name)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        logger.info(f"Saving {len(od_final)} tract pairs to {output_path}")
        od_final.to_csv(output_path)
    return od_final


def od_path(state_code, interim_data_path=None):
    abbr = state_dict[state_code].lower()
    return os.path.join(interim_data_path or INTERIM_DATA_DIR, 'od', f'{abbr}-tract-od-2020.csv')
