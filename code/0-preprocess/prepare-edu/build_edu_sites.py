"""Build <state>_school_id.gpkg and <state>_daycare_id.gpkg for the synthesis driver.

Source (--source epa2015, the default and the one Jiang et al. 2024 cite, ref. 20):
  "Educational Institutions, US, 2015, ORNL, SEGS", procured by EPA OEI from
  Oak Ridge National Laboratory.
    metadata: https://catalog.data.gov/dataset/educational-institutions-us-2015-ornl-segs
              https://edg.epa.gov/metadata/catalog/search/resource/details.page?uuid=%7B9C49AE4B-F175-43D0-BCC6-A928FF54C329%7D
    download: https://edg.epa.gov/data/Public/OEI/ORNL_Education/ORNL_Education.zip
              (FileGDB 'Education.gdb', EPSG:4326, server last-modified 2015-08-10)
    service:  https://geodata.epa.gov/arcgis/rest/services/OEI/ORNL_Education/MapServer

  Layer mapping:
    schools  <- PublicSchools + PrivateSchools  (have LEVEL and ENROLLMENT)
    daycare  <- DayCareCenters                  (no ENROLLMENT; POPULATION is used)
    not used:   CollegesUniversities, SupplementalColleges (school assignment covers ages 5-17 only)

Output fields read by src/assign_education_site.py:
  eduID, geometry, LATITUDE, LONGITUDE, s_age, e_age, ENROLLMENT, count (=0).
  eduID is '<state FIPS>s<n>' for schools and '<state FIPS>d<n>' for daycare, because
  src/create_social_networks.py selects school and daycare members with
  wp.str.contains('s') / ('d') and workers with contains('w').
  Extra provenance columns: SRC_LAYER, SRC_ID, NAME, LEVEL, ENROLLMENT_SRC, ENR_MISSING.

Run:
  python code/0-preprocess/prepare-edu/build_edu_sites.py --state ut [--download]
Reads  RAW_DATA_DIR/edu/epa2015/ORNL_Education.zip (or --raw PATH: any OGR datasource with
       the layer names above, e.g. the extracted Education.gdb)
Writes PROCESSED_DATA_DIR/edu/<state>_school_id.gpkg and <state>_daycare_id.gpkg
"""
import argparse
import os
import sys

import geopandas as gpd
import pandas as pd
import requests
from loguru import logger

from src.cli import resolve_state_codes
from src.preprocess_data import __school_start_age__, __school_end_age__
from src.settings import RAW_DATA_DIR, PROCESSED_DATA_DIR, state_dict

EPA2015_URL = 'https://edg.epa.gov/data/Public/OEI/ORNL_Education/ORNL_Education.zip'
EPA2015_ZIP = os.path.join(RAW_DATA_DIR, 'edu', 'epa2015', 'ORNL_Education.zip')
EPA2015_GDB = 'Education.gdb'

SCHOOL_LAYERS = [('PublicSchools', 'NCESID'), ('PrivateSchools', 'NCESID')]
DAYCARE_LAYER = ('DayCareCenters', 'ID')

# Same CRS as the TIGER tracts (<state>-tracts-demo-work.shp.zip) that
# assign_education_site.py buffers and intersects against.
OUTPUT_CRS = 'EPSG:4269'

# Paper Step 2: daycare is ages 0-4. The daycare branch of the assignment module
# does not read these, but the fields are written so both tables share one schema.
DAYCARE_S_AGE, DAYCARE_E_AGE = 0, 4

OUTPUT_COLUMNS = ['eduID', 'SRC_LAYER', 'SRC_ID', 'NAME', 'LEVEL', 'LATITUDE', 'LONGITUDE',
                  's_age', 'e_age', 'ENROLLMENT', 'ENROLLMENT_SRC', 'ENR_MISSING', 'count', 'geometry']


def download_epa2015(dest=EPA2015_ZIP, url=EPA2015_URL):
    """Download the ORNL/EPA 2015 zip (about 22.6 MB) with TLS verification on."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    logger.info(f"Downloading {url} -> {dest}")
    tmp = dest + '.part'
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(tmp, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    os.replace(tmp, dest)
    return dest


def _datasource(raw_path):
    """OGR path for the raw data: a zip holding Education.gdb, or any datasource path."""
    if raw_path.lower().endswith('.zip'):
        return f"zip://{os.path.abspath(raw_path)}!{EPA2015_GDB}"
    return raw_path


def _read_layer(raw_path, layer, state_abbr):
    gdf = gpd.read_file(_datasource(raw_path), layer=layer, where=f"STATE = '{state_abbr.upper()}'")
    logger.info(f"{layer}: {len(gdf)} {state_abbr.upper()} records")
    return gdf


def _clean_enrollment(values):
    """Integer ENROLLMENT; null/negative source codes (e.g. -1, -2, -9) become 0.

    Returns (enrollment, source_value, missing_flag). A site with ENROLLMENT 0 never
    passes the assignment module's `count < ENROLLMENT` check, so it is only used by
    the over-capacity fallback.
    """
    src = pd.to_numeric(values, errors='coerce')
    missing = src.isna() | (src < 0)
    enrollment = src.where(~missing, 0).round().astype('int64')
    return enrollment, src.astype('Int64'), missing


def _finish(gdf, state_code, marker):
    """Sort deterministically, add eduID/count, reproject, and order columns."""
    gdf = gdf.sort_values(['SRC_LAYER', 'SRC_ID'], kind='stable').reset_index(drop=True)
    gdf = gdf.to_crs(OUTPUT_CRS)
    # coordinates used for distance ranking are taken from the written geometry
    gdf['LONGITUDE'] = gdf.geometry.x
    gdf['LATITUDE'] = gdf.geometry.y
    gdf['eduID'] = [f"{state_code}{marker}{i:05d}" for i in range(1, len(gdf) + 1)]
    gdf['count'] = 0
    gdf['count'] = gdf['count'].astype('int64')
    return gpd.GeoDataFrame(gdf[OUTPUT_COLUMNS], geometry='geometry', crs=OUTPUT_CRS)


def _drop_bad_geometry(gdf, layer):
    bad = gdf.geometry.isna() | gdf.geometry.is_empty
    if bad.any():
        logger.warning(f"{layer}: dropping {int(bad.sum())} records without a location")
    return gdf[~bad]


def build_school(raw_path, state_code):
    state_abbr = state_dict[state_code]
    parts = []
    for layer, id_col in SCHOOL_LAYERS:
        gdf = _drop_bad_geometry(_read_layer(raw_path, layer, state_abbr), layer)
        enrollment, src, missing = _clean_enrollment(gdf['ENROLLMENT'])
        part = gpd.GeoDataFrame({
            'SRC_LAYER': layer,
            'SRC_ID': gdf[id_col].astype(str),
            'NAME': gdf['NAME'],
            'LEVEL': gdf['LEVEL'],
            'ENROLLMENT': enrollment,
            'ENROLLMENT_SRC': src,
            'ENR_MISSING': missing,
        }, geometry=gdf.geometry, crs=gdf.crs)
        # existing LEVEL -> age-band helpers (Primary/Elementary 5-11, Middle 12-14,
        # Secondary 12-17, High 15-17, anything else 5-17)
        part['s_age'] = part.apply(__school_start_age__, axis=1).astype('int64')
        part['e_age'] = part.apply(__school_end_age__, axis=1).astype('int64')
        parts.append(part)
    school = pd.concat(parts, ignore_index=True)
    school = gpd.GeoDataFrame(school, geometry='geometry', crs=parts[0].crs)
    return _finish(school, state_code, 's')


def build_daycare(raw_path, state_code):
    state_abbr = state_dict[state_code]
    layer, id_col = DAYCARE_LAYER
    gdf = _drop_bad_geometry(_read_layer(raw_path, layer, state_abbr), layer)
    # The daycare layer has no ENROLLMENT field; POPULATION (the centre's
    # reported population/capacity) is used as the enrollment bound.
    enrollment, src, missing = _clean_enrollment(gdf['POPULATION'])
    daycare = gpd.GeoDataFrame({
        'SRC_LAYER': layer,
        'SRC_ID': gdf[id_col].astype(str),
        'NAME': gdf['NAME'],
        'LEVEL': 'Daycare',
        'ENROLLMENT': enrollment,
        'ENROLLMENT_SRC': src,
        'ENR_MISSING': missing,
        's_age': DAYCARE_S_AGE,
        'e_age': DAYCARE_E_AGE,
    }, geometry=gdf.geometry, crs=gdf.crs)
    return _finish(daycare, state_code, 'd')


def _summarise(name, gdf):
    logger.info(f"{name}: {len(gdf)} sites, {int(gdf['ENR_MISSING'].sum())} with missing/negative "
                f"enrollment set to 0, total ENROLLMENT {int(gdf['ENROLLMENT'].sum())}")


def build_epa2015(state_code, raw_path=None, out_dir=None, download=False):
    raw_path = raw_path or EPA2015_ZIP
    out_dir = out_dir or os.path.join(PROCESSED_DATA_DIR, 'edu')
    if not os.path.exists(raw_path):
        if download and raw_path == EPA2015_ZIP:
            download_epa2015(raw_path)
        else:
            raise FileNotFoundError(
                f"{raw_path} not found; download {EPA2015_URL} there or pass --download")
    abbr = state_dict[state_code].lower()
    os.makedirs(out_dir, exist_ok=True)
    outputs = {}
    for kind, build in (('school', build_school), ('daycare', build_daycare)):
        gdf = build(raw_path, state_code)
        _summarise(f"{abbr} {kind}", gdf)
        path = os.path.join(out_dir, f"{abbr}_{kind}_id.gpkg")
        if os.path.exists(path):
            os.remove(path)
        gdf.to_file(path, driver='GPKG', layer=f"{abbr}_{kind}_id")
        logger.info(f"Wrote {path}")
        outputs[kind] = path
    return outputs


def build_nces_ccd(state_code, **kwargs):
    raise NotImplementedError(
        "--source nces_ccd (USBE/NCES Common Core of Data replacement for the 2015 ORNL layer) "
        "is not implemented yet; use --source epa2015 to reproduce Jiang et al. 2024")


SOURCES = {'epa2015': build_epa2015, 'nces_ccd': build_nces_ccd}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Build school and daycare GeoPackages')
    parser.add_argument('--state', default='ut',
                        help="state abbreviation or 2-digit FIPS (default: ut)")
    parser.add_argument('--source', choices=sorted(SOURCES), default='epa2015',
                        help='education-site source (default: epa2015, the layer the paper used)')
    parser.add_argument('--raw', default=None,
                        help=f'raw input (default: {EPA2015_ZIP})')
    parser.add_argument('--out-dir', default=None,
                        help="output directory (default: PROCESSED_DATA_DIR/edu)")
    parser.add_argument('--download', action='store_true',
                        help='download the raw zip to the default location if it is missing')
    args = parser.parse_args(argv)
    try:
        codes = resolve_state_codes(args.state)
    except argparse.ArgumentTypeError as e:
        parser.error(str(e))
    for code in codes:
        SOURCES[args.source](code, raw_path=args.raw, out_dir=args.out_dir, download=args.download)
    return 0


if __name__ == '__main__':
    sys.exit(main())
