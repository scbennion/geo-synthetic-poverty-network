import gzip
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

import src.preprocess_data as pp

ROOT = Path(__file__).resolve().parent.parent
PREP = ROOT / 'code' / '0-preprocess' / 'prepare-commute-data'

# block-level LODES rows (w_geocode, h_geocode, S000). Two blocks in the same tract pair
# must be summed; the aux row has an out-of-state (Idaho) home.
UT_MAIN = [('490351001001000', '490351002001000', 3),
           ('490351001001001', '490351002001002', 4),
           ('490490001001000', '490351001001000', 5)]
UT_AUX = [('490351001001000', '160010001001000', 2)]

CBP_HEADER = ('#GEOCOMP|GEOTYPE|ST|COUNTY|CSA|MSA|ZIPCODE|CD116|GEO_ID|GEO_LABEL|GEO_ID_F|NAICS2017|'
              'NAICS2017_LABEL|NAICS2017_F|LFO|LFO_LABEL|EMPSZES|EMPSZES_LABEL|YEAR|ESTAB')


def _cbp_row(geo_id, label, estab, naics='00', lfo='001', empszes='001'):
    return f'00|02|49|000|000|00000|00000|00|{geo_id}|{label}||{naics}|x||{lfo}|x|{empszes}|x|2020|{estab}'


CBP_ROWS = [
    _cbp_row('0400000US49', 'Utah', 150),
    _cbp_row('0500000US49035', 'Salt Lake County, Utah', 100),
    _cbp_row('0500000US49035', 'Salt Lake County, Utah', 60, empszes='210'),   # size class
    _cbp_row('0500000US49035', 'Salt Lake County, Utah', 7, naics='11'),       # one industry
    _cbp_row('0500000US49049', 'Utah County, Utah', 50),
    _cbp_row('0500000US01001', 'Autauga County, Alabama', 9),
    _cbp_row('8610000US49035', 'ZIP 49035', 999),   # ZIP row whose last 5 digits look like a county
    _cbp_row('310M400US41620', 'Salt Lake City metro', 120),
]


def _write_lodes(raw, st, kind, rows):
    (raw / 'work_commute').mkdir(parents=True, exist_ok=True)
    with gzip.open(raw / 'work_commute' / f'{st}_od_{kind}_JT00_2020.csv.gz', 'wt') as f:
        f.write('w_geocode,h_geocode,S000,SA01\n')
        for w, h, n in rows:
            f.write(f'{w},{h},{n},0\n')


def _write_cbp_zip(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('CB2000CBP.dat', '\n'.join([CBP_HEADER] + CBP_ROWS) + '\n')


def _run(script, data_dir, *args):
    env = dict(os.environ, GSPN_DATA_DIR=str(data_dir), PYTHONPATH=str(ROOT))
    return subprocess.run([sys.executable, str(PREP / script), *args], cwd=PREP,
                          env=env, capture_output=True, text=True)


# ---------- LODES ----------

def test_combine_aggregates_blocks_to_tracts(tmp_path):
    _write_lodes(tmp_path / 'raw', 'ut', 'main', UT_MAIN)
    _write_lodes(tmp_path / 'raw', 'ut', 'aux', UT_AUX)
    od = pp.combine_in_out_county_data('ut', '49', inter_data_dir=tmp_path / 'interim',
                                       raw_data_dir=tmp_path / 'raw', processed_data_dir=tmp_path / 'processed')
    got = {(r.work, r.home): r.S000 for r in od.itertuples()}
    assert got == {('49035100100', '49035100200'): 7,
                   ('49049000100', '49035100100'): 5,
                   ('49035100100', '16001000100'): 2}
    # the same file feeds the workplace counts (interim) and the synthesis driver (processed)
    for d in ('interim', 'processed'):
        written = pd.read_csv(tmp_path / d / 'od' / 'ut-tract-od-2020.csv', dtype={'work': str, 'home': str})
        assert sorted(zip(written.work, written.home, written.S000)) == sorted(
            (w, h, n) for (w, h), n in got.items())


def test_combine_keeps_leading_zeros(tmp_path):
    # Alabama (01): the old code read geocodes as numbers and kept 10-digit tract IDs
    _write_lodes(tmp_path / 'raw', 'al', 'main', [('010010201001000', '010010202001000', 1)])
    _write_lodes(tmp_path / 'raw', 'al', 'aux', [])
    od = pp.combine_in_out_county_data('al', '01', inter_data_dir=tmp_path / 'interim',
                                       raw_data_dir=tmp_path / 'raw', processed_data_dir=tmp_path / 'processed')
    assert list(od.work) == ['01001020100'] and list(od.home) == ['01001020200']


def test_combine_requires_both_files(tmp_path):
    _write_lodes(tmp_path / 'raw', 'ut', 'main', UT_MAIN)
    with pytest.raises(FileNotFoundError, match='aux'):
        pp.combine_in_out_county_data('ut', '49', inter_data_dir=tmp_path / 'interim',
                                      raw_data_dir=tmp_path / 'raw', processed_data_dir=tmp_path / 'processed')


def test_lodes_download_failure_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(pp, 'download_file', lambda url, path: False)
    with pytest.raises(RuntimeError, match='ut_od_main_JT00_2020'):
        pp.download_lodes_2020_data('ut', raw_data_dir=str(tmp_path))


def test_lodes_download_verifies_certificates(tmp_path, monkeypatch):
    calls = []

    def fake_get(url, stream, verify, timeout):
        calls.append(verify)
        raise pp.requests.exceptions.ConnectionError('offline')

    monkeypatch.setattr(pp.requests, 'get', fake_get)
    with pytest.raises(RuntimeError):
        pp.download_lodes_2020_data('ut', raw_data_dir=str(tmp_path))
    assert calls == [True]


# ---------- CBP ----------

def test_cbp_county_rows_only(tmp_path):
    _write_cbp_zip(tmp_path / 'CB2000CBP.zip')
    cbp = pp.read_cbp_counties(str(tmp_path / 'CB2000CBP.zip'))
    assert cbp.to_dict('list') == {
        'county': ['01001', '49035', '49049'],
        'NAME': ['Autauga County, Alabama', 'Salt Lake County, Utah', 'Utah County, Utah'],
        'ESTAB': [9, 100, 50]}


def test_cbp_unzipped_dat_matches_zip(tmp_path):
    _write_cbp_zip(tmp_path / 'CB2000CBP.zip')
    zipfile.ZipFile(tmp_path / 'CB2000CBP.zip').extractall(tmp_path)
    pd.testing.assert_frame_equal(pp.read_cbp_counties(str(tmp_path / 'CB2000CBP.dat')),
                                  pp.read_cbp_counties(str(tmp_path / 'CB2000CBP.zip')))


def test_cbp_data_census_gov_csv(tmp_path):
    # data.census.gov export: a second header row of labels, county rows only if selected
    rows = [{'GEO_ID': 'Geography', 'NAME': 'Geographic Area Name', 'NAICS2017': 'x',
             'EMPSZES_LABEL': 'x', 'ESTAB': 'x'},
            {'GEO_ID': '0500000US49035', 'NAME': 'Salt Lake County, Utah', 'NAICS2017': '00',
             'EMPSZES_LABEL': 'All establishments', 'ESTAB': '100'},
            {'GEO_ID': '0500000US49035', 'NAME': 'Salt Lake County, Utah', 'NAICS2017': '00',
             'EMPSZES_LABEL': 'Establishments with less than 5 employees', 'ESTAB': '60'},
            {'GEO_ID': '8610000US49035', 'NAME': 'ZIP 49035', 'NAICS2017': '00',
             'EMPSZES_LABEL': 'All establishments', 'ESTAB': '999'}]
    pd.DataFrame(rows).to_csv(tmp_path / 'cbp.csv', index=False)
    cbp = pp.read_cbp_counties(str(tmp_path / 'cbp.csv'))
    assert cbp.to_dict('list') == {'county': ['49035'], 'NAME': ['Salt Lake County, Utah'], 'ESTAB': [100]}


def test_cbp_duplicate_county_raises(tmp_path):
    path = tmp_path / 'dup.dat'
    path.write_text('\n'.join([CBP_HEADER, CBP_ROWS[1], CBP_ROWS[1]]) + '\n')
    with pytest.raises(ValueError, match='49035'):
        pp.read_cbp_counties(str(path))


# ---------- drivers, raw files to synthesis inputs ----------

def test_commute_chain_to_workplace_json(tmp_path):
    raw = tmp_path / 'raw-data'
    _write_lodes(raw, 'ut', 'main', UT_MAIN)
    _write_lodes(raw, 'ut', 'aux', UT_AUX)
    _write_cbp_zip(raw / 'workplace' / 'CB2000CBP.zip')
    # per-state tract file as written by process_census_shp.py --state ut (no all-states file)
    census = tmp_path / 'interim-data' / 'census'
    census.mkdir(parents=True)
    gpd.GeoDataFrame({'GEOID': ['49035100100', '49035100200', '49049000100'], 'STATEFP': ['49'] * 3},
                     geometry=[box(i, 0, i + 1, 1) for i in range(3)], crs='EPSG:4326'
                     ).to_file(census / 'ut_census_demo_4326.shp.zip', driver='ESRI Shapefile')

    for script, args in [('process_lodes8.py', ['--state', 'ut', '--skip-download']),
                         ('process_cbp.py', []),
                         ('build_tract_workplace_json.py', ['--state', 'ut', '--seed', '1'])]:
        result = _run(script, tmp_path, *args)
        assert result.returncode == 0, f'{script}: {result.stderr}'

    # the synthesis driver's OD input exists and reads back with full tract IDs
    od = pd.read_csv(tmp_path / 'processed-data' / 'od' / 'ut-tract-od-2020.csv', dtype={'work': str, 'home': str})
    assert set(od.work) == {'49035100100', '49049000100'}

    wp = pd.read_json(tmp_path / 'processed-data' / 'us_tract_number_work.json', orient='records', lines=True,
                      dtype={'GEOID': str}).set_index('GEOID')
    # 49035: ESTAB 100, jobs 7 + 2 all in 49035100100; 49049: ESTAB 50, all 5 jobs in 49049000100
    assert wp['WP_CNT'].to_dict() == {'49035100100': 100, '49035100200': 0, '49049000100': 50}
