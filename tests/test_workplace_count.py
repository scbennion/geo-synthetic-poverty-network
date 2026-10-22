import gzip
import os
import subprocess
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from src.preprocess_data import county_fips, get_number_of_wp, tract_and_county_jobs

ROOT = Path(__file__).resolve().parent.parent
DRIVER = ROOT / 'code' / '0-preprocess' / 'prepare-commute-data' / 'build_tract_workplace_json.py'

# 2 counties, 4 tracts. 49035: ESTAB 100, jobs 30 + 70. 49049: ESTAB 50, jobs 10 + 30.
ESTAB = {'49035': 100, '49049': 50}
JOBS = {'49035100100': 30, '49035100200': 70, '49049000100': 10, '49049000200': 30}
# floor(B_c * J_t / J_c)
EXPECTED = {'49035100100': 30, '49035100200': 70, '49049000100': 12, '49049000200': 37}


def _od(jobs):
    # split each tract's jobs over two home tracts so the helper has to sum them
    rows = []
    for work, n in jobs.items():
        rows += [{'work': work, 'home': '49035100100', 'S000': n - n // 2},
                 {'work': work, 'home': '49049000100', 'S000': n // 2}]
    return pd.DataFrame(rows)


def _cbp(estab):
    return pd.DataFrame({'county': list(estab), 'NAME': list(estab), 'ESTAB': list(estab.values())})


def _wp_cnt(geoid, od, cbp, errors):
    return get_number_of_wp(pd.Series({'GEOID': geoid}), od, cbp, geoid[:2], errors)


def test_wp_cnt_per_tract_uses_own_county():
    od, cbp, errors = _od(JOBS), _cbp(ESTAB), []
    got = {t: _wp_cnt(t, od, cbp, errors) for t in JOBS}
    assert got == EXPECTED
    assert errors == []


def test_county_sum_never_exceeds_estab():
    od, cbp, errors = _od(JOBS), _cbp(ESTAB), []
    totals = {}
    for t in JOBS:
        totals[county_fips(t)] = totals.get(county_fips(t), 0) + _wp_cnt(t, od, cbp, errors)
    for c, total in totals.items():
        assert total <= ESTAB[c]


def test_order_of_od_rows_does_not_matter():
    # the old helper used the first grouped county total; reversing rows must not change anything
    od = _od(JOBS).iloc[::-1].reset_index(drop=True)
    assert {t: _wp_cnt(t, od, _cbp(ESTAB), []) for t in JOBS} == EXPECTED


def test_precomputed_jobs_match():
    od, cbp = _od(JOBS), _cbp(ESTAB)
    jobs = tract_and_county_jobs(od)
    for t in JOBS:
        assert get_number_of_wp(pd.Series({'GEOID': t}), od, cbp, '49', [], jobs=jobs) == EXPECTED[t]


def test_leading_zero_state_restored():
    # Alabama: OD 'work' and CBP 'county' as written after int parsing (leading zero lost)
    od = pd.DataFrame({'work': ['1001020100', '1001020200'], 'home': ['1001020100'] * 2, 'S000': [1, 3]})
    cbp = pd.DataFrame({'county': [1001], 'NAME': ['x'], 'ESTAB': [8]})
    assert _wp_cnt('01001020100', od, cbp, []) == 2
    assert _wp_cnt('01001020200', od, cbp, []) == 6


def test_missing_inputs_give_zero_and_error():
    od, cbp, errors = _od(JOBS), _cbp({'49035': 100}), []
    assert _wp_cnt('49049000100', od, cbp, errors) == 0          # county not in CBP
    assert _wp_cnt('49035999999', od, cbp, errors) == 0          # tract has no OD jobs
    assert errors == ['49049000100', '49035999999']


# ---------- end-to-end driver ----------

OUT_OF_STATE = '16001000100'   # Idaho work tract listed in the Utah aux file


def _write_fixture(d):
    (d / 'interim-data' / 'cbp').mkdir(parents=True)
    (d / 'interim-data' / 'census').mkdir(parents=True)
    (d / 'interim-data' / 'od').mkdir(parents=True)
    (d / 'raw-data' / 'work_commute').mkdir(parents=True)

    cbp = _cbp({**ESTAB, '16001': 9})
    cbp['county'] = cbp['county'].astype(int)  # as process_cbp.py output is read back
    cbp.to_csv(d / 'interim-data' / 'cbp' / 'workplace_cbp.csv')

    gpd.GeoDataFrame({'GEOID': list(JOBS) + ['16001000200'], 'STATEFP': ['49'] * 4 + ['16']},
                     geometry=[box(i, 0, i + 1, 1) for i in range(5)], crs='EPSG:4326'
                     ).to_file(d / 'interim-data' / 'census' / 'census_demo_4326.shp.zip', driver='ESRI Shapefile')

    _od(JOBS).to_csv(d / 'interim-data' / 'od' / 'ut-tract-od-2020.csv')
    pd.DataFrame({'work': [OUT_OF_STATE, '16001000200'], 'home': ['16001000100'] * 2, 'S000': [1, 2]}
                 ).to_csv(d / 'interim-data' / 'od' / 'id-tract-od-2020.csv')

    with gzip.open(d / 'raw-data' / 'work_commute' / 'ut_od_aux_JT00_2020.csv.gz', 'wt') as f:
        f.write('w_geocode,h_geocode,S000\n'
                '490351001001000,160010001001000,5\n'
                f'{OUT_OF_STATE}1000,490351001001000,1\n')


def _run(d, *args):
    env = dict(os.environ, GSPN_DATA_DIR=str(d), PYTHONPATH=str(ROOT))
    return subprocess.run([sys.executable, str(DRIVER), *args], cwd=DRIVER.parent,
                          env=env, capture_output=True, text=True)


def _read(path):
    # read exactly as run-synthesis-by-state.py does
    df = pd.read_json(path, orient='records', lines=True)
    df['GEOID'] = df['GEOID'].astype(str)
    return df.set_index('GEOID')


def test_driver_end_to_end(tmp_path):
    _write_fixture(tmp_path)
    result = _run(tmp_path, '--seed', '1')
    assert result.returncode == 0, result.stderr
    df = _read(tmp_path / 'processed-data' / 'us_tract_number_work.json')

    # Utah tracts plus the aux out-of-state destination; not the other Idaho tract
    assert sorted(df.index) == sorted(list(JOBS) + [OUT_OF_STATE])
    assert df['WP_CNT'].to_dict() == {**EXPECTED, OUT_OF_STATE: 3}  # floor(9 * 1/3)
    for geoid, row in df.iterrows():
        assert len(row.WP_PROBA) == row.WP_CNT
        assert np.isclose(sum(row.WP_PROBA), 1.0)
    errors = pd.read_csv(tmp_path / 'processed-data' / 'workplaces_error' / 'ut-tract-number-work-error.csv')
    assert errors.empty


def test_driver_counties_subset(tmp_path):
    _write_fixture(tmp_path)
    result = _run(tmp_path, '--state', 'ut', '--counties', '049',
                  '--output', str(tmp_path / 'out.json'))
    assert result.returncode == 0, result.stderr
    df = _read(tmp_path / 'out.json')
    assert sorted(df.index) == ['16001000100', '49049000100', '49049000200']
    assert df.loc['49049000100', 'WP_CNT'] == 12 and df.loc['49049000200', 'WP_CNT'] == 37
