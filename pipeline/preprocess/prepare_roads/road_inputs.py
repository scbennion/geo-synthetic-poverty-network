"""Download TIGER county roads and prepare the cleaned state road input."""
import os
import re

import geopandas as gpd
import pandas as pd
import requests
from bs4 import BeautifulSoup
from loguru import logger
from tqdm import tqdm

from pipeline.preprocess._downloads import download_file
from src.settings import RAW_DATA_DIR, INTERIM_DATA_DIR, PROCESSED_DATA_DIR


def get_road_file_names(base_url, state_fips_code):
    """
    Get the road file names for a specific state.

    Parameters:
    - base_url (str): The base URL for the road files.
    - state_fips_code (str): The FIPS code for the state of interest.
    """
    try:
        logger.info(
            f"Getting road file names for state FIPS code {state_fips_code} from {base_url}"
        )
        response = requests.get(base_url)
        response.raise_for_status()

        # Parse the webpage
        soup = BeautifulSoup(response.text, "html.parser")

        # Regex pattern to match the road files for the given state
        pattern = re.compile(f"tl_2020_{state_fips_code}[0-9]+_roads.zip")

        # Extract all matching road files
        road_files = []
        for link in soup.find_all("a", href=True):
            match = pattern.match(link["href"])
            if match:
                road_files.append(match.group(0))

        logger.info(
            f"Found {len(road_files)} road files for state FIPS code {state_fips_code}"
        )
        return road_files

    except Exception as e:
        print(f"An error occurred: {e}")
        return None


def download_and_prepare_road_data(
    state_fips_code,
    state_name,
    raw_data_path=RAW_DATA_DIR,
    interim_data_path=INTERIM_DATA_DIR,
    counties=None,
    output_name=None,
):
    """
    Download the TIGER/Line 2020 All Roads county files for a state and combine them
    into one interim shapefile, ``<interim>/road/<output_name>_road.shp.zip``.

    Parameters:
    - state_fips_code (str): 2-digit state FIPS code, e.g. '49'.
    - state_name (str): state abbreviation, e.g. 'UT'.
    - raw_data_path (str): county ZIPs are cached in ``<raw>/road/<state_name>/``.
    - interim_data_path (str): where the combined shapefile is written.
    - counties (list[str] | None): 3-digit county FIPS codes to keep; None = all.
    - output_name (str | None): output file prefix; defaults to ``state_name``.

    Returns the output path. Downloads verify TLS certificates; a failed download
    raises instead of being skipped silently.
    """
    output_name = output_name or state_name
    output_path = f"{interim_data_path}/road/{output_name}_road.shp.zip"
    if os.path.exists(output_path):
        logger.info(
            f"Cached output found at {output_path}. Skipping download and processing."
        )
        return output_path

    logger.info("Downloading and processing road data.")
    os.makedirs(f"{raw_data_path}/road/{state_name}", exist_ok=True)
    os.makedirs(f"{interim_data_path}/road", exist_ok=True)

    list_ = []
    url = "https://www2.census.gov/geo/tiger/TIGER2020/ROADS/"

    road_file_names = get_road_file_names(url, state_fips_code)
    if not road_file_names:
        raise RuntimeError(f"No road files found for state {state_fips_code} at {url}")
    if counties is not None:
        wanted = {f"tl_2020_{state_fips_code}{c}_roads.zip" for c in counties}
        missing = wanted - set(road_file_names)
        if missing:
            raise RuntimeError(f"Road files not listed at {url}: {sorted(missing)}")
        road_file_names = [f for f in road_file_names if f in wanted]

    for file_name in tqdm(road_file_names):
        file_path = f"{raw_data_path}/road/{state_name}/{file_name}"
        if not os.path.exists(file_path):
            if not download_file(url + file_name, file_path):
                raise RuntimeError(f"Failed to download {url + file_name}")
        list_.append(gpd.read_file(file_path))

    frame = pd.concat(list_, axis=0, ignore_index=True)

    # Save the processed data
    frame.to_file(output_path)
    logger.info(f"Saved road data to {output_path}")
    return output_path


def process_interim_road_data(
    state_name,
    interim_data_path=INTERIM_DATA_DIR,
    processed_data_path=PROCESSED_DATA_DIR,
    output_name=None,
    overwrite=False,
):
    """
    Clean the interim road shapefile and write the synthesis input
    ``<processed>/road/<output_name>_road_cleaned.shp.zip`` (fields LINEARID,
    MTFCC, comp, geometry; CRS of the TIGER input, EPSG:4269).

    Cleaning is the pure-Python replacement for the former GRASS GIS step, see
    ``prepare_roads.road_cleaning.clean_road_network``.

    Parameters:
    - state_name (str): state abbreviation, e.g. 'UT'.
    - interim_data_path (str): reads ``<interim>/road/<output_name>_road.shp.zip``.
    - processed_data_path (str): directory for the processed shapefile.
    - output_name (str | None): file prefix; defaults to ``state_name``.
    - overwrite (bool): rebuild even if the output exists.

    Returns the output path.
    """
    from pipeline.preprocess.prepare_roads.road_cleaning import clean_road_network

    output_name = output_name or state_name
    output_dir = f"{processed_data_path}/road"
    output_path = f"{output_dir}/{output_name}_road_cleaned.shp.zip"
    if os.path.exists(output_path) and not overwrite:
        logger.info(f"Cached road data found at {output_path}. Skipping processing.")
        return output_path

    input_path = f"{interim_data_path}/road/{output_name}_road.shp.zip"
    if not os.path.exists(input_path):
        raise FileNotFoundError(
            f"Interim road file {input_path} does not exist; "
            "run python -m pipeline.preprocess.prepare_roads.download_process_roads first."
        )
    logger.info(f"Reading interim roads from {input_path}")
    raw = gpd.read_file(input_path)
    logger.info(f"Cleaning {len(raw)} road features")
    roads = clean_road_network(raw)
    logger.info(f"Cleaned roads: {len(roads)} segments, {roads['comp'].nunique()} components")

    os.makedirs(output_dir, exist_ok=True)
    logger.info(f"Saving processed data to {output_path}")
    roads.to_file(output_path)
    return output_path
