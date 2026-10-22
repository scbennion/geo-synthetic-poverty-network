"""Census preprocessing on small synthetic fixtures (no network)."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from src import census_prep as cp
from src.ctreate_individuals import __create_individuals__

ROOT = Path(__file__).resolve().parent.parent
PROCESS = ROOT / 'code' / '0-preprocess' / 'prepare-census' / 'process_census_shp.py'

UT_TRACTS = ['49035100100', '49035100200', '49049000100']
ID_TRACT = '16001000100'  # another state, must be filtered out

# required by assign_household (group quarters, household types), in this order
REQUIRED_HHOLD = ['DP1_0127C', 'DP1_0128C', 'DP1_0130C', 'DP1_0131C', 'DP1_0132C'] + \
                 [f'DP1_{i:04d}C' for i in range(133, 145)]
MALE_GROUPS = [f'DP1_{i:04d}C' for i in range(26, 44)]
FEMALE_GROUPS = [f'DP1_{i:04d}C' for i in range(50, 68)]


def _dp1_value(col, t):
    return int(col[4:8]) % 7 + 1 + t


def _dp1_frame(geoids):
    """Columns GEO_ID, NAME, then every DP1 count and percent column, deliberately shuffled."""
    cols = {}
    for t, g in enumerate(geoids):
        cols.setdefault('GEO_ID', []).append(f'1400000US{g}')
        cols.setdefault('NAME', []).append(f'Census Tract {g}')
        for i in range(1, 161):
            cols.setdefault(f'DP1_{i:04d}C', []).append(str(_dp1_value(f'DP1_{i:04d}C', t)))
            cols.setdefault(f'DP1_{i:04d}P', []).append('1.5')
    df = pd.DataFrame(cols)
    dp = [c for c in df.columns if c.startswith('DP1_')]
    return df[['GEO_ID', 'NAME'] + dp[::-1]]


def _write_national_dp1(path, geoids):
    """data.census.gov download layout: label row, a non-tract row, trailing empty column."""
    df = _dp1_frame(geoids)
    labels = pd.DataFrame([['Geography', 'Geographic Area Name'] + ['Count!!label'] * (df.shape[1] - 2)],
                          columns=df.columns)
    state = df.iloc[[0]].copy()
    state['GEO_ID'] = '0400000US49'
    out = pd.concat([labels, state, df], ignore_index=True)
    out[''] = ''
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False)


def _tiger_tracts(geoids):
    rows = []
    for i, g in enumerate(geoids):
        rows.append({'STATEFP': g[:2], 'COUNTYFP': g[2:5], 'TRACTCE': g[5:], 'GEOID': g, 'NAME': g[5:],
                     'NAMELSAD': f'Census Tract {g[5:]}', 'MTFCC': 'G5020', 'FUNCSTAT': 'S',
                     'ALAND': 1000 + i, 'AWATER': 0, 'INTPTLAT': '+40.0', 'INTPTLON': '-111.0'})
    geoms = [box(-112 + 0.01 * i, 40, -112 + 0.01 * i + 0.01, 40.01) for i in range(len(geoids))]
    return gpd.GeoDataFrame(rows, geometry=geoms, crs='EPSG:4269')


def _write_zip(gdf, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + '.shp.zip')
    gdf.to_file(tmp, driver='ESRI Shapefile')
    shutil.move(tmp, path)


def _write_fixture(data_dir, commute=True):
    raw, interim = data_dir / 'raw-data', data_dir / 'interim-data'
    dp1 = Path(cp.dp1_state_csv_path('49', str(raw)))
    dp1.parent.mkdir(parents=True)
    _dp1_frame(UT_TRACTS).to_csv(dp1, index=False)
    _write_zip(_tiger_tracts(UT_TRACTS + [ID_TRACT]), Path(cp.tiger_tract_zip_path('49', str(raw))))
    urban = gpd.GeoDataFrame({'UACE20': ['1', '2'], 'NAME20': ['Near, UT', 'Far, ME']},
                             geometry=[box(-112.005, 40.0, -111.995, 40.005), box(-70, 44, -69, 45)],
                             crs='EPSG:4269')
    _write_zip(urban, Path(cp.urban_zip_path(str(raw))))
    if commute:
        od = Path(cp.od_path('49', str(interim)))
        od.parent.mkdir(parents=True)
        pd.DataFrame({'work': UT_TRACTS, 'home': UT_TRACTS, 'S000': [30, 10, 20]}).to_csv(od)
        cbp = Path(cp.cbp_path(str(interim)))
        cbp.parent.mkdir(parents=True)
        pd.DataFrame({'county': ['49035', '49049'], 'NAME': ['Salt Lake', 'Utah'], 'ESTAB': [8, 5]}).to_csv(cbp)


def _run(data_dir, *args):
    env = dict(os.environ, GSPN_DATA_DIR=str(data_dir),
               PYTHONPATH=os.pathsep.join([str(ROOT), os.environ.get('PYTHONPATH', '')]))
    return subprocess.run([sys.executable, str(PROCESS), *args], cwd=PROCESS.parent, env=env,
                          capture_output=True, text=True)


def test_dp1_column_lists():
    assert cp.DP1_COLUMNS[:2] == ['DP1_0001C', 'DP1_0025C']
    assert cp.DP1_COLUMNS[2:20] == MALE_GROUPS
    assert cp.DP1_COLUMNS[20:39] == ['DP1_0049C'] + FEMALE_GROUPS
    idx = [cp.DP1_COLUMNS.index(c) for c in REQUIRED_HHOLD]
    assert idx == sorted(idx)


def test_read_dp1_national_layout(tmp_path):
    path = tmp_path / 'DECENNIALDP2020.DP1-Data.csv'
    _write_national_dp1(path, UT_TRACTS)
    df = cp.read_dp1(path)
    assert list(df.columns) == ['GEOID'] + cp.DP1_COLUMNS
    assert list(df['GEOID']) == UT_TRACTS  # label and state rows dropped, no tract lost
    assert (df[cp.DP1_COLUMNS].dtypes == 'int64').all()
    assert df.loc[1, 'DP1_0132C'] == _dp1_value('DP1_0132C', 1)


def test_process_state_writes_both_files(tmp_path):
    _write_fixture(tmp_path)
    result = _run(tmp_path, '--state', 'ut')
    assert result.returncode == 0, result.stderr

    work = gpd.read_file(cp.tracts_demo_work_path('49', str(tmp_path / 'processed-data')))
    assert sorted(work['GEOID']) == UT_TRACTS
    assert work.crs.to_epsg() == 4326
    cols = list(work.columns)
    assert cols[:12] == cp.TIGER_TRACT_COLUMNS
    assert cols[12:12 + len(cp.DP1_COLUMNS)] == cp.DP1_COLUMNS
    assert cols[-2:] == ['WP_CNT', 'geometry']
    positions = [cols.index(c) for c in REQUIRED_HHOLD]
    assert positions == sorted(positions)
    # 8 Salt Lake establishments split 30:10 by jobs. Utah County (049) is not asserted: the
    # current get_number_of_wp divides by the first county's job total (Agent C's fix).
    wp = dict(zip(work['GEOID'], work['WP_CNT']))
    assert (wp['49035100100'], wp['49035100200']) == (6, 2)

    # exactly how run-synthesis-by-state.py and __create_individuals__ index a tract
    tract = work.sort_values('GEOID').set_index('GEOID').iloc[0]
    assert list(tract[13:50].drop(['DP1_0049C']).index) == MALE_GROUPS + FEMALE_GROUPS
    people = __create_individuals__(tract)
    assert len(people) == sum(_dp1_value(c, 0) for c in MALE_GROUPS + FEMALE_GROUPS)
    assert (people.gender == 'm').sum() == sum(_dp1_value(c, 0) for c in MALE_GROUPS)
    # src/verification.py indexes the frame with GEOID as a column
    assert list(work.iloc[:, 14:51].drop('DP1_0049C', axis=1).columns) == MALE_GROUPS + FEMALE_GROUPS

    urban = gpd.read_file(cp.urban_gpkg_path('49', str(tmp_path / 'processed-data')))
    assert list(urban['NAME20']) == ['Near, UT']
    assert urban.crs.to_epsg() == 4326

    demo = gpd.read_file(cp.census_demo_path('49', str(tmp_path / 'interim-data')))
    assert demo.crs.to_epsg() == 4269 and len(demo) == 3


def test_missing_commute_inputs(tmp_path):
    _write_fixture(tmp_path, commute=False)
    result = _run(tmp_path, '--state', 'ut')
    assert result.returncode == 3
    assert 'commute inputs' in result.stderr
    assert not os.path.exists(cp.tracts_demo_work_path('49', str(tmp_path / 'processed-data')))
    assert os.path.exists(cp.census_demo_path('49', str(tmp_path / 'interim-data'), '_4326'))
    assert os.path.exists(cp.urban_gpkg_path('49', str(tmp_path / 'processed-data')))
    assert _run(tmp_path, '--state', 'ut', '--skip-work').returncode == 0


def test_fetch_dp1_without_key_uses_data_census_gov(monkeypatch):
    frame = _dp1_frame(UT_TRACTS)
    rows = [list(frame.columns)] + frame.values.tolist()
    calls = []

    class Response:
        status_code = 200
        headers = {}

        def raise_for_status(self):
            pass

        def json(self):
            return {'response': {'data': rows, 'dataAPIURI': 'x'}}

    def fake_get(url, params=None, **kwargs):
        calls.append((url, params))
        return Response()

    monkeypatch.delenv('CENSUS_API_KEY', raising=False)
    monkeypatch.setattr(cp.requests, 'get', fake_get)
    df = cp.fetch_dp1_tracts('49')
    assert calls[0][0] == cp.DATA_CENSUS_GOV_URL
    assert calls[0][1]['g'] == '040XX00US49$1400000'
    assert list(df.columns[:4]) == ['GEO_ID', 'NAME', 'DP1_0001C', 'DP1_0001P']
    assert len(df) == 3
