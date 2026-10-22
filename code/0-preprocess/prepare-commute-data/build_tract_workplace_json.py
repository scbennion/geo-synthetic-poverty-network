"""
Build processed-data/us_tract_number_work.json (GEOID, WP_CNT, WP_PROBA), the
workplace metadata that run-synthesis-by-state.py reads as JSON lines.

Scope: the tracts of --state (optionally only --counties), plus any out-of-state
work tracts that appear in that state's LODES `aux` file. WP_CNT comes from
src.preprocess_data.get_number_of_wp, i.e. floor(ESTAB_c * J_t / J_c) with J_t and
J_c taken from the work side of the tract's own state's OD table; WP_PROBA from
src.tools.wp_proba.

Inputs (settings paths):
  INTERIM_DATA_DIR/cbp/workplace_cbp.csv                 (process_cbp.py)
  INTERIM_DATA_DIR/census/census_demo_4326.shp.zip       (tract list, GEOID/STATEFP)
  INTERIM_DATA_DIR/od/<st>-tract-od-2020.csv             (process_lodes8.py)
  RAW_DATA_DIR/work_commute/<st>_od_aux_JT00_2020.csv.gz (LODES8 aux)
Outputs:
  PROCESSED_DATA_DIR/us_tract_number_work.json (or --output)
  PROCESSED_DATA_DIR/workplaces_error/<run>-tract-number-work-error.csv
"""
import argparse
import os

import geopandas as gpd
import numpy as np
import pandas as pd
from loguru import logger

from src.cli import add_geography_args, resolve_geography, run_name
from src.preprocess_data import get_number_of_wp, tract_and_county_jobs, tract_geoid
from src.settings import INTERIM_DATA_DIR, PROCESSED_DATA_DIR, RAW_DATA_DIR, state_dict
from src.tools import wp_proba


def read_od(state_code):
    path = os.path.join(INTERIM_DATA_DIR, f"od/{state_dict[state_code].lower()}-tract-od-2020.csv")
    if not os.path.exists(path):
        return None
    return pd.read_csv(path, dtype={'work': str, 'home': str})


def aux_destination_tracts(state_code):
    """Work tracts outside `state_code` listed in that state's LODES aux file."""
    path = os.path.join(RAW_DATA_DIR, 'work_commute',
                        f"{state_dict[state_code].lower()}_od_aux_JT00_2020.csv.gz")
    if not os.path.exists(path):
        logger.warning(f"No LODES aux file at {path}; no out-of-state destinations added.")
        return []
    aux = pd.read_csv(path, dtype={'w_geocode': str}, usecols=['w_geocode'])
    tracts = aux['w_geocode'].str.zfill(15).str[:11].unique()
    return sorted(t for t in tracts if t[:2] != state_code)


def build(state_code, counties=None):
    cbp = pd.read_csv(os.path.join(INTERIM_DATA_DIR, 'cbp/workplace_cbp.csv'), dtype={'county': str})
    cbp['county'] = cbp['county'].str.zfill(5)

    census = gpd.read_file(os.path.join(INTERIM_DATA_DIR, 'census/census_demo_4326.shp.zip'))
    geoids = census.loc[census['STATEFP'].astype(str).str.zfill(2) == state_code, 'GEOID'].map(tract_geoid)
    if counties is not None:
        geoids = geoids[geoids.str[2:5].isin(counties)]
    tracts = sorted(set(geoids) | set(aux_destination_tracts(state_code)))

    error_tract = []
    rows = []
    by_state = {}
    for geoid in tracts:
        st = geoid[:2]
        if st not in by_state:
            od = read_od(st)
            # J_t and J_c always come from the full OD of the tract's own state,
            # never from a county subset.
            by_state[st] = None if od is None else (od, tract_and_county_jobs(od))
            if od is None:
                logger.warning(f"No OD table for state {st}; its tracts get WP_CNT=0.")
        if by_state[st] is None:
            error_tract.append(geoid)
            wp_cnt = 0
        else:
            od, jobs = by_state[st]
            wp_cnt = get_number_of_wp(pd.Series({'GEOID': geoid}), od, cbp, st, error_tract, jobs=jobs)
        rows.append({'GEOID': geoid, 'WP_CNT': int(wp_cnt), 'WP_PROBA': wp_proba(int(wp_cnt)).tolist()})

    return pd.DataFrame(rows, columns=['GEOID', 'WP_CNT', 'WP_PROBA']), error_tract


def main(argv=None):
    parser = add_geography_args(argparse.ArgumentParser(description=__doc__.split('\n\n')[0]))
    parser.set_defaults(state='ut')
    parser.add_argument('--output', default=os.path.join(PROCESSED_DATA_DIR, 'us_tract_number_work.json'))
    parser.add_argument('--seed', type=int, default=None,
                        help='seed numpy.random before drawing WP_PROBA (default: unseeded, as before)')
    args = parser.parse_args(argv)
    codes, counties = resolve_geography(args)
    if len(codes) != 1:
        parser.error('--state must name a single state')
    state_code = codes[0]
    if args.seed is not None:
        np.random.seed(args.seed)

    df, error_tract = build(state_code, counties)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    df.to_json(args.output, orient='records', lines=True)
    logger.info(f"Wrote {len(df)} tracts to {args.output}")

    error_dir = os.path.join(PROCESSED_DATA_DIR, 'workplaces_error')
    os.makedirs(error_dir, exist_ok=True)
    error_path = os.path.join(error_dir, f"{run_name(state_dict[state_code].lower(), counties)}-tract-number-work-error.csv")
    pd.DataFrame(error_tract, columns=['tract']).to_csv(error_path, index=False)
    logger.info(f"{len(error_tract)} tracts with WP_CNT=0 due to missing inputs; listed in {error_path}")


if __name__ == '__main__':
    main()
