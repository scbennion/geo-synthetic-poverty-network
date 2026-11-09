import re
import os
import zipfile
import pandas as pd
import geopandas as gpd
from tqdm import tqdm
import requests

from bs4 import BeautifulSoup
from loguru import logger

from src.settings import RAW_DATA_DIR, INTERIM_DATA_DIR, PROCESSED_DATA_DIR


def get_all_census_shp_name(base_url):
    """
    Get the road file names for a specific state.

    Parameters:
    - base_url (str): The base URL for the road files.
    - state_fips_code (str): The FIPS code for the state of interest.
    """
    try:
        logger.info(
            f"Getting census names from {base_url}"
        )
        response = requests.get(base_url)
        response.raise_for_status()

        # Parse the webpage
        soup = BeautifulSoup(response.text, "html.parser")

        # Regex pattern to match the road files for the given state
        pattern = re.compile(f"tl_2020_[0-9]+_tract.zip")

        # Extract all matching road files
        census_files = []
        for link in soup.find_all("a", href=True):
            match = pattern.match(link["href"])
            if match:
                census_files.append(match.group(0))

        logger.info(
            f"Found {len(census_files)} census files USA"
        )
        return census_files

    except Exception as e:
        print(f"An error occurred: {e}")
        return None


def download_and_prepare_census_shp_data(
    raw_data_path=RAW_DATA_DIR,
    interim_data_path=INTERIM_DATA_DIR,
):
    """
    Download and prepare road data for a specific state and save the resulting shapefile.

    Parameters:
    - state_name (str): The name of the state.
    - state_fips_code (str): The FIPS code for the state of interest.
    - raw_data_path (str): The path to the raw road shapefiles.
                           Default is `src.settings.RAW_DATA_DIR`.
    - interim_data_path (str): The directory where the resulting shapefile will be saved.
                               Default is `src.settings.INTERIM_DATA_DIR`.
    """

    # Check for cached output
    output_path = f"{interim_data_path}/census/all_census.shp.zip"
    if os.path.exists(output_path):
        logger.info(
            f"Cached output found at {output_path}. Skipping download and processing."
        )
        return

    logger.info("Downloading and processing census tract shp data.")
    # Create the directory if it doesn't exist
    if not os.path.exists(f"{raw_data_path}/census/"):
        os.makedirs(f"{raw_data_path}/census/")
    if not os.path.exists(f"{interim_data_path}/census"):
        os.makedirs(f"{interim_data_path}/census")

    list_ = []
    url = "https://www2.census.gov/geo/tiger/TIGER2020/TRACT/"

    census_file_names = get_all_census_shp_name(url)

    for file_name in tqdm(census_file_names):
        file_path = f"{raw_data_path}/census/{file_name}"
        # logger.info(
        #     f"Downloading {file_name} Census Tract Shp data to {file_path}."
        # )
        if not os.path.exists(file_path):
            try:
                full_url = url + file_name
                #wget.download(full_url, out=f"{raw_data_path}/road/{state_name}", no_check_certificate=True)
                download_file(full_url, f"{raw_data_path}/census/{file_name}", verify_ssl=False)
            except Exception as e:
                if str(e) == "HTTP Error 404: Not Found":
                    continue
                else:
                    logger.error(f"Error {e} when downloading file {file_name}")
                    continue
        try:
            gdf = gpd.read_file(file_path, index_col=None, header=0)
            list_.append(gdf)
        except Exception as e:
            logger.error(f"Error {e} when reading file {file_name}")

    frame = pd.concat(list_, axis=0, ignore_index=True)

    # Save the processed data
    frame.to_file(output_path)
    logger.info(f"Saved census data to {output_path}")

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


# old name, kept so existing callers keep working
richard_download_and_prepare_road_data = download_and_prepare_road_data


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
    ``src.clean_roads.clean_road_network``.

    Parameters:
    - state_name (str): state abbreviation, e.g. 'UT'.
    - interim_data_path (str): reads ``<interim>/road/<output_name>_road.shp.zip``.
    - processed_data_path (str): directory for the processed shapefile.
    - output_name (str | None): file prefix; defaults to ``state_name``.
    - overwrite (bool): rebuild even if the output exists.

    Returns the output path.
    """
    from src.clean_roads import clean_road_network

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
            "run code/0-preprocess/prepare-road/download_process_roads.py first."
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


def download_file(url, output_path, verify_ssl=True):
    """Download ``url`` to ``output_path``; returns True on success, False on error.

    TLS certificates are verified unless ``verify_ssl=False`` is passed. The file is
    written to ``<output_path>.part`` and renamed only when complete, so a failed
    download never leaves a truncated file that later looks cached.
    """
    part_path = f"{output_path}.part"
    try:
        response = requests.get(url, stream=True, verify=verify_ssl, timeout=60)
        response.raise_for_status()

        with open(part_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        os.replace(part_path, output_path)
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Error downloading {url}: {e}")
        if os.path.exists(part_path):
            os.remove(part_path)
        return False


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


CBP_URL = "https://www2.census.gov/programs-surveys/cbp/data/2020/CB2000CBP.zip"


def read_cbp_counties(path):
    """
    One row per county from 2020 County Business Patterns: `county` (5-digit FIPS),
    `NAME`, `ESTAB`, for all industries (NAICS2017 00), all legal forms (LFO 001) and
    all establishment sizes (EMPSZES 001).

    Accepts the paper's pipe-delimited CB2000CBP.zip / CB2000CBP.dat (streamed, not
    extracted) or a data.census.gov table CSV (CBP2020.CB2000CBP-Data.csv). Only
    county geographies (GEO_ID 0500000US...) are kept; the national file also holds
    ZIP-code, metro and state rows whose last five characters can look like a county.
    """
    if path.endswith((".zip", ".dat")):
        cols = ["GEO_ID", "GEO_LABEL", "NAICS2017", "LFO", "EMPSZES", "ESTAB"]
        if path.endswith(".zip"):
            with zipfile.ZipFile(path) as z:
                with z.open(z.namelist()[0]) as f:
                    cbp = _filter_cbp_chunks(pd.read_csv(f, sep="|", usecols=cols, dtype=str, chunksize=2_000_000))
        else:
            cbp = _filter_cbp_chunks(pd.read_csv(path, sep="|", usecols=cols, dtype=str, chunksize=2_000_000))
        cbp = cbp[(cbp["LFO"] == "001") & (cbp["EMPSZES"] == "001")].rename(columns={"GEO_LABEL": "NAME"})
    else:
        cbp = pd.read_csv(path, dtype=str)
        cbp = cbp[cbp["GEO_ID"].str.startswith("0500000US", na=False)
                  & (cbp["NAICS2017"] == "00")
                  & (cbp["EMPSZES_LABEL"] == "All establishments")]
        if "LFO" in cbp.columns:
            cbp = cbp[cbp["LFO"] == "001"]
    cbp = cbp.assign(county=cbp["GEO_ID"].str[-5:], ESTAB=cbp["ESTAB"].astype(int))
    cbp = cbp[["county", "NAME", "ESTAB"]].sort_values("county").reset_index(drop=True)
    if cbp["county"].duplicated().any():
        raise ValueError(f"CBP has more than one all-establishments row for counties "
                         f"{sorted(cbp.loc[cbp['county'].duplicated(), 'county'])[:5]}")
    return cbp


def _filter_cbp_chunks(chunks):
    return pd.concat(ch[ch["GEO_ID"].str.startswith("0500000US") & (ch["NAICS2017"] == "00")] for ch in chunks)


def tract_geoid(value):
    """11-digit tract GEOID string, restoring leading zeros lost to int parsing."""
    s = str(value).strip()
    if s.endswith('.0'):
        s = s[:-2]
    return s.zfill(11)


def county_fips(geoid):
    """5-digit county FIPS (state + county) of a tract GEOID, leading zeros preserved."""
    return tract_geoid(geoid)[:5]


def tract_and_county_jobs(od):
    """
    Jobs located in each work tract (J_t) and in each county (J_c) from an OD table
    with 'work' tract and 'S000' columns. Returns two Series indexed by 11-digit
    tract GEOID and 5-digit county FIPS.
    """
    work = od['work'].map(tract_geoid)
    tract_jobs = od['S000'].groupby(work).sum()
    county_jobs = tract_jobs.groupby(tract_jobs.index.str[:5]).sum()
    return tract_jobs, county_jobs


def get_number_of_wp(data, od, campany_df, state_code, error_tract, jobs=None):
    """
    Number of workplaces for a tract: floor(B_c * J_t / J_c), where B_c is the CBP
    establishment count (ESTAB) of the tract's own county, J_t the jobs located in the
    tract and J_c the jobs located in that county (both from the OD 'work' side).

    The county is the first 5 digits of the 11-digit GEOID for every state;
    `state_code` is kept for call compatibility. Pass `jobs` (the result of
    `tract_and_county_jobs(od)`) to avoid regrouping `od` for every tract.
    Tracts with no OD jobs, no CBP county row, or zero county jobs return 0 and
    are appended to `error_tract`, as before.
    """
    tract_number = str(data.GEOID)
    try:
        tract_jobs, county_jobs = jobs if jobs is not None else tract_and_county_jobs(od)
        geoid = tract_geoid(tract_number)
        county_number = geoid[:5]

        tract_jobs_number = int(tract_jobs.loc[geoid])
        county_job_number = int(county_jobs.loc[county_number])

        estab = campany_df.loc[campany_df['county'].map(lambda c: str(c).zfill(5)) == county_number, 'ESTAB']
        county_company_number = int(estab.values[0])
        return int(county_company_number * (tract_jobs_number / county_job_number))

    except Exception:
        logger.info(f"{tract_number} has issue")
        error_tract.append(tract_number)
        return 0


# Add starting and ending age for schools
def __school_start_age__(row):
    '''
    Assign School starting age and end age based on school type School
    Function to get start age for schools
    :param row:
    :return: age
    '''
    if row.LEVEL in ['Primary', 'Elementary']:
        start_a = 5

    elif row.LEVEL in ['Middle']:
        start_a = 12

    elif row.LEVEL in ['Secondary']:
        start_a = 12

    elif row.LEVEL in ['High']:
        start_a = 15

    else:
        start_a = 5
    return start_a  # , end_a


def __school_end_age__(row):
    '''
    Function to get end age for schools
    :param row:
    :return: age
    '''
    if row.LEVEL in ['Primary', 'Elementary']:
        end_a = 11

    elif row.LEVEL in ['Middle']:
        end_a = 14

    elif row.LEVEL in ['Secondary']:
        end_a = 17

    elif row.LEVEL in ['High']:
        end_a = 17

    else:
        end_a = 17
    return end_a
