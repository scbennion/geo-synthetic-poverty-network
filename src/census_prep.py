"""Census tract inputs for one state: DP1 demographic profile, TIGER tracts, urban areas.

Order of the census preprocessing steps (see code/0-preprocess/prepare-census/):

1. ``download_census_inputs.py --state ut`` fetches, into ``RAW_DATA_DIR``:
   - ``demographic-profile-20/DECENNIALDP2020.DP1-ut-tracts.csv``: 2020 Demographic
     Profile table DP1 for every tract in the state (Census API dataset
     ``2020/dec/dp``, ``group(DP1)``; columns named ``DP1_0001C`` etc., the same
     names as a data.census.gov table download);
   - ``census/tl_2020_49_tract.zip``: 2020 TIGER/Line tract boundaries;
   - ``urban/tl_2020_us_uac20.zip``: 2020 TIGER/Line urban areas (national file).
2. ``process_census_shp.py --state ut`` joins DP1 to the tracts and writes
   ``INTERIM_DATA_DIR/census/ut_census_demo.shp.zip`` (EPSG:4269, as TIGER ships it),
   ``INTERIM_DATA_DIR/census/ut_census_demo_4326.shp.zip`` (the reprojected copy that
   ``add_tract_workplaces.py`` reads) and ``PROCESSED_DATA_DIR/urban/UT_urban.gpkg``.
   If the commute inputs exist it also writes
   ``PROCESSED_DATA_DIR/census/ut-tracts-demo-work.shp.zip``.
3. The ``-work`` file adds ``WP_CNT`` (workplaces per tract), which
   ``src/create_space.py::__create_work_location__`` needs. It requires
   ``INTERIM_DATA_DIR/cbp/workplace_cbp.csv`` (``process_cbp.py``) and
   ``INTERIM_DATA_DIR/od/ut-tract-od-2020.csv`` (``process_lodes8.py``).

Column order matters: ``__create_individuals__`` reads the 36 age/sex counts as
``tract[13:50]`` (minus ``DP1_0049C``) of a row whose index is GEOID and whose last
field is geometry, so the file must hold exactly the 11 TIGER attribute columns
(without GEOID) then ``DP1_0001C``, ``DP1_0025C``, ``DP1_0026C``...
"""
import os

import geopandas as gpd
import pandas as pd
import requests
from loguru import logger

from src.settings import INTERIM_DATA_DIR, PROCESSED_DATA_DIR, RAW_DATA_DIR, state_dict

# CRS of the -work tract file and the urban file. TIGER ships EPSG:4269 (NAD83);
# add_tract_workplaces.py has always read a 'census_demo_4326' file, so the
# reprojection to EPSG:4326 (WGS84) is reproduced here.
TARGET_CRS = 'EPSG:4326'

# TIGER/Line 2020 tract attributes in the order the TIGER file has them.
TIGER_TRACT_COLUMNS = ['STATEFP', 'COUNTYFP', 'TRACTCE', 'GEOID', 'NAME', 'NAMELSAD',
                       'MTFCC', 'FUNCSTAT', 'ALAND', 'AWATER', 'INTPTLAT', 'INTPTLON']

# Sex and age: total, male total + 18 male age groups (0026-0043), female total +
# 18 female age groups (0050-0067). Same list as Jiang et al.'s process_census_shp.py.
DEMO_COLUMNS = ['DP1_0001C'] + [f'DP1_{i:04d}C' for i in range(25, 44)] + \
               [f'DP1_{i:04d}C' for i in range(49, 68)]

# Relationship / group quarters (0112-0131) and households by type (0132-0146).
HHOLD_COLUMNS = [f'DP1_{i:04d}C' for i in range(112, 147)]

DP1_COLUMNS = DEMO_COLUMNS + HHOLD_COLUMNS

TRACT_GEO_PREFIX = '1400000US'

DP1_API_URL = 'https://api.census.gov/data/2020/dec/dp'
DATA_CENSUS_GOV_URL = 'https://data.census.gov/api/access/data/table'
TIGER_TRACT_URL = 'https://www2.census.gov/geo/tiger/TIGER2020/TRACT/tl_2020_{code}_tract.zip'
URBAN_URL = 'https://www2.census.gov/geo/tiger/TIGER2020/UAC/{name}'
URBAN_FILE = 'tl_2020_us_uac20.zip'


# ---------------------------------------------------------------- paths

def dp1_state_csv_path(state_code, raw_data_path=None):
    abbr = state_dict[state_code].lower()
    return os.path.join(raw_data_path or RAW_DATA_DIR, 'demographic-profile-20',
                        f'DECENNIALDP2020.DP1-{abbr}-tracts.csv')


def dp1_national_csv_path(raw_data_path=None):
    """The national data.census.gov download the original pipeline read."""
    return os.path.join(raw_data_path or RAW_DATA_DIR, 'demographic-profile-20',
                        'DECENNIALDP2020.DP1-Data.csv')


def tiger_tract_zip_path(state_code, raw_data_path=None):
    return os.path.join(raw_data_path or RAW_DATA_DIR, 'census', f'tl_2020_{state_code}_tract.zip')


def national_tract_path(interim_data_path=None):
    """All-US tract boundaries written by download_census_shp.py."""
    return os.path.join(interim_data_path or INTERIM_DATA_DIR, 'census', 'all_census.shp.zip')


def urban_zip_path(raw_data_path=None, name=URBAN_FILE):
    return os.path.join(raw_data_path or RAW_DATA_DIR, 'urban', name)


def census_demo_path(state_code, interim_data_path=None, crs_suffix=''):
    abbr = state_dict[state_code].lower()
    return os.path.join(interim_data_path or INTERIM_DATA_DIR, 'census',
                        f'{abbr}_census_demo{crs_suffix}.shp.zip')


def tracts_demo_work_path(state_code, processed_data_path=None):
    abbr = state_dict[state_code].lower()
    return os.path.join(processed_data_path or PROCESSED_DATA_DIR, 'census',
                        f'{abbr}-tracts-demo-work.shp.zip')


def urban_gpkg_path(state_code, processed_data_path=None):
    return os.path.join(processed_data_path or PROCESSED_DATA_DIR, 'urban',
                        f'{state_dict[state_code].upper()}_urban.gpkg')


def od_path(state_code, interim_data_path=None):
    abbr = state_dict[state_code].lower()
    return os.path.join(interim_data_path or INTERIM_DATA_DIR, 'od', f'{abbr}-tract-od-2020.csv')


def cbp_path(interim_data_path=None):
    return os.path.join(interim_data_path or INTERIM_DATA_DIR, 'cbp', 'workplace_cbp.csv')


# ---------------------------------------------------------------- downloads

def download(url, output_path, timeout=300):
    """Stream url to output_path. TLS certificates are verified (requests' default)."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    tmp = output_path + '.part'
    with requests.get(url, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        with open(tmp, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1 << 16):
                f.write(chunk)
    os.replace(tmp, output_path)
    return output_path


def _rows_to_frame(rows):
    df = pd.DataFrame(rows[1:], columns=rows[0])
    keep = ['GEO_ID', 'NAME'] + sorted(c for c in df.columns if c.startswith('DP1_'))
    return df[keep]


def fetch_dp1_tracts(state_code, api_key=None, timeout=300):
    """DP1 for every tract in the state, as strings, columns GEO_ID, NAME, DP1_*.

    With a Census API key (argument or env CENSUS_API_KEY) this queries
    api.census.gov directly. Without one it uses the data.census.gov table
    endpoint, which serves the same API query (its response names
    ``https://api.census.gov/data/2020/dec/dp?get=group(DP1)``) without a key.
    api.census.gov now redirects every keyless request to missing_key.html.
    """
    api_key = api_key or os.environ.get('CENSUS_API_KEY')
    if api_key:
        params = {'get': 'group(DP1)', 'for': 'tract:*', 'in': f'state:{state_code}', 'key': api_key}
        response = requests.get(DP1_API_URL, params=params, timeout=timeout, allow_redirects=False)
        response.raise_for_status()
        if response.status_code != 200:
            raise RuntimeError(f'Census API returned {response.status_code} ({response.headers.get("Location")})')
        rows = response.json()
    else:
        params = {'id': 'DECENNIALDP2020.DP1', 'g': f'040XX00US{state_code}$1400000'}
        response = requests.get(DATA_CENSUS_GOV_URL, params=params, timeout=timeout)
        response.raise_for_status()
        payload = response.json()['response']
        logger.info(f"data.census.gov source: {payload.get('dataAPIURI')}")
        rows = payload['data']
    return _rows_to_frame(rows)


def download_dp1_tracts(state_code, raw_data_path=None, api_key=None):
    out = dp1_state_csv_path(state_code, raw_data_path)
    df = fetch_dp1_tracts(state_code, api_key=api_key)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    df.to_csv(out, index=False)
    logger.info(f'DP1: {len(df)} tracts saved to {out}')
    return out


def download_tiger_tracts(state_code, raw_data_path=None):
    out = tiger_tract_zip_path(state_code, raw_data_path)
    if not os.path.exists(out):
        download(TIGER_TRACT_URL.format(code=state_code), out)
    return out


def download_urban_areas(raw_data_path=None, name=URBAN_FILE):
    out = urban_zip_path(raw_data_path, name)
    if not os.path.exists(out):
        download(URBAN_URL.format(name=name), out)
    return out


# ---------------------------------------------------------------- processing

def read_dp1(path):
    """GEOID plus DP1_COLUMNS (int), from a DP1 CSV.

    Accepts both the data.census.gov download layout (a second header row of
    labels, a trailing empty column) and the per-state file written by
    download_dp1_tracts. Rows whose GEO_ID is not a tract are dropped.
    """
    dp_df = pd.read_csv(path, dtype=str)
    dp_df = dp_df.loc[:, ~dp_df.columns.str.startswith('Unnamed')]
    dp_df = dp_df[dp_df['GEO_ID'].str.startswith(TRACT_GEO_PREFIX, na=False)].copy()
    missing = [c for c in DP1_COLUMNS if c not in dp_df.columns]
    if missing:
        raise ValueError(f'{path} lacks DP1 columns: {missing}')
    dp_df['GEOID'] = dp_df['GEO_ID'].str[-11:]
    out = dp_df.loc[:, ['GEOID'] + DP1_COLUMNS].reset_index(drop=True)
    out[DP1_COLUMNS] = out[DP1_COLUMNS].apply(pd.to_numeric, errors='raise').astype('int64')
    return out


def join_tracts_dp1(boundary, demo_df, state_codes):
    """TIGER tracts for state_codes joined to DP1, columns in the order the synthesis needs."""
    missing = [c for c in TIGER_TRACT_COLUMNS if c not in boundary.columns]
    if missing:
        raise ValueError(f'tract boundaries lack columns: {missing}')
    boundary = boundary.loc[boundary['STATEFP'].isin(list(state_codes)),
                            TIGER_TRACT_COLUMNS + [boundary.geometry.name]]
    census_shp = boundary.merge(demo_df, on='GEOID', how='inner')
    unmatched = len(boundary) - len(census_shp)
    if unmatched:
        logger.warning(f'{unmatched} tract boundaries have no DP1 row and were dropped')
    census_shp = census_shp[TIGER_TRACT_COLUMNS + DP1_COLUMNS + [boundary.geometry.name]]
    return gpd.GeoDataFrame(census_shp, geometry=boundary.geometry.name, crs=boundary.crs)


def state_urban_areas(urban, state_tracts, crs=TARGET_CRS):
    """Urban-area polygons intersecting the state's tracts (unclipped), in crs."""
    tracts = state_tracts.to_crs(urban.crs)
    area = tracts.geometry.union_all()
    selected = urban[urban.geometry.intersects(area)]
    return selected.to_crs(crs).reset_index(drop=True)


def add_workplace_counts(state_census, od_df, cbp, state_code):
    """Adds WP_CNT using get_number_of_wp; returns (gdf, error_tracts). Same as add_tract_workplaces.py."""
    from src.preprocess_data import get_number_of_wp
    state_census = state_census.copy()
    error_tract = []
    state_census['WP_CNT'] = state_census.apply(get_number_of_wp, args=(od_df, cbp, state_code, error_tract),
                                                axis=1)
    return state_census, error_tract


def read_cbp(path):
    cbp = pd.read_csv(path).iloc[:, 1:]
    cbp['county'] = cbp['county'].astype(str)
    return cbp


def write_shp_zip(gdf, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    gdf.to_file(path, driver='ESRI Shapefile')
    logger.info(f'Saved {len(gdf)} rows to {path}')
