"""Synthesis output -> social networks -> validation, on a 3-tract Utah fixture.

Real synthesis inputs are not in the repository, so the population GeoPackage is
built here with the same columns, id formats and CRS the synthesis driver writes
(it goes through ``src.tools.__collect_results__`` and ``to_file(..., driver='GPKG')``
exactly as ``run-synthesis-by-state.py`` does). The network and validation drivers
are then run as subprocesses against it with ``GSPN_DATA_DIR`` pointing at tmp.
"""
import csv
import os
import subprocess
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, box

from src.population_io import population_source, read_population
from src.tools import __collect_results__

ROOT = Path(__file__).resolve().parent.parent
NETWORKS = ROOT / 'code' / '2-social-networks'
VALIDATION = ROOT / 'code' / '3-validation'

# two Salt Lake (035) tracts and one Utah County (049) tract with people; one more
# Salt Lake tract that "failed" in synthesis (listed in the error log, no people)
TRACTS = ['49035100100', '49035100200', '49049000100']
FAILED_TRACT = '49035100300'
PER_GROUP = 2          # people per 5-year age/sex group in each tract
HHOLD_SIZE = 3

# DP1 column layout: the census helpers select age/sex columns by position
# (file columns 14:51 = 18 male groups, DP1_0049C, 18 female groups), so the
# fixture keeps 14 leading columns. Names other than the DP1 ones used by the
# helpers are placeholders.
LEADING = ['GEOID', 'STATEFP', 'COUNTYFP', 'TRACTCE', 'NAME', 'ALAND', 'AWATER',
           'INTPTLAT', 'INTPTLON', 'DP1_0001C', 'DP1_0025C', 'X1', 'X2', 'X3']
MALE = [f'DP1_{n:04d}C' for n in range(31, 49)]
FEMALE = [f'DP1_{n:04d}C' for n in range(50, 68)]
HHOLD_COLS = ['DP1_0127C', 'DP1_0128C', 'DP1_0130C', 'DP1_0131C', 'DP1_0132C'] + \
             [f'DP1_{n:04d}C' for n in range(133, 145)]
CENSUS_HHOLDS = {'DP1_0133C': 3, 'DP1_0134C': 1}   # -> 2 type-0 and 1 type-1 per tract


def _census(data_dir):
    rows = []
    for i, geoid in enumerate(TRACTS + [FAILED_TRACT]):
        row = dict.fromkeys(LEADING + MALE + ['DP1_0049C'] + FEMALE + HHOLD_COLS, 0)
        row.update(GEOID=geoid, STATEFP=geoid[:2], COUNTYFP=geoid[2:5], TRACTCE=geoid[5:], NAME=geoid,
                   DP1_0001C=36 * PER_GROUP, DP1_0025C=18 * PER_GROUP, DP1_0049C=18 * PER_GROUP,
                   DP1_0132C=4, **CENSUS_HHOLDS)
        row.update({c: PER_GROUP for c in MALE + FEMALE})
        row['geometry'] = box(-112 + i * 0.01, 40.7, -112 + (i + 1) * 0.01, 40.71)
        rows.append(row)
    gdf = gpd.GeoDataFrame(rows, geometry='geometry', crs='EPSG:4269')
    out = data_dir / 'processed-data' / 'census'
    out.mkdir(parents=True, exist_ok=True)
    gdf.to_file(out / 'ut-tracts-demo-work.shp.zip', driver='ESRI Shapefile')
    return gdf


def _tract_people(geoid, minx):
    """People for one tract in the shape __synthesize__ leaves them before collection."""
    ages, genders = [], []
    for code in range(36):
        ages += [(code % 18) * 5] * PER_GROUP
        genders += ['m' if code < 18 else 'f'] * PER_GROUP
    people = pd.DataFrame({'code': range(len(ages)), 'age': ages, 'gender': genders})
    people.index = geoid + 'i' + people.index.astype(str)
    people['assigned'] = 1
    n_hholds = len(people) // HHOLD_SIZE
    people['hhold'] = [geoid + 'h' + str(min(k // HHOLD_SIZE, n_hholds)) for k in range(len(people))]
    people['htype'] = [11 if k // HHOLD_SIZE >= n_hholds else (k // HHOLD_SIZE) % 11 for k in range(len(people))]
    homes = {h: Point(minx + 0.0001 * j, 40.705) for j, h in enumerate(people.hhold.unique())}
    people['geometry'] = people.hhold.map(homes)
    wp = []
    for k, (age, hh) in enumerate(zip(people.age, people.hhold)):
        if age <= 4:
            wp.append(f'd{k % 2}')                    # daycare eduID
        elif age <= 17:
            wp.append(f's{k % 3}')                    # school eduID
        elif k % 2 == 0:
            dest = TRACTS[k % len(TRACTS)]
            wp.append(f'{dest}w{k % 4}' if k % 10 else f'{dest}wNone')
        else:
            wp.append(None)                           # not employed
    people['wp'] = wp
    people['urban'] = True
    return people


def _population_gpkg(path, tracts):
    """Write a population GeoPackage the way run-synthesis-by-state.py does."""
    people = [_tract_people(g, -112 + TRACTS.index(g) * 0.01) for g in tracts]
    population_df = __collect_results__(people, 'Pop')
    population_df['wp'] = population_df['wp'].fillna(population_df['hhold'])  # missing-wp branch
    path.parent.mkdir(parents=True, exist_ok=True)
    population_df.to_file(path, driver='GPKG')
    return population_df


@pytest.fixture
def data_dir(tmp_path):
    _census(tmp_path)
    ut = tmp_path / 'results-data' / 'ut'
    _population_gpkg(ut / 'ut_population.gpkg', TRACTS)
    (ut / 'ut_error_log.csv').write_text(f',tract,error_message\n0,{FAILED_TRACT},boom\n')
    return tmp_path


def _run(script, data_dir, *args):
    env = dict(os.environ, GSPN_DATA_DIR=str(data_dir), PYTHONPATH=str(ROOT), MPLBACKEND='Agg')
    result = subprocess.run([sys.executable, str(script), *args], cwd=script.parent, env=env,
                            capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stderr[-3000:]
    assert 'An error occurred' not in result.stderr, result.stderr[-3000:]
    return result


def _network(path):
    with open(path) as f:
        return {row[0]: row[1:] for row in csv.reader(f) if row}


def test_reader_preserves_synthesis_fields(tmp_path):
    written = _population_gpkg(tmp_path / 'ut_population.gpkg', TRACTS)
    read = read_population(tmp_path / 'ut_population.gpkg')
    for col in ['id', 'hhold', 'htype', 'wp', 'geometry', 'long', 'lat', 'urban', 'age', 'gender']:
        assert col in read.columns
    assert read.crs == 'EPSG:4269'
    assert read['id'].tolist() == written['id'].tolist()
    assert read['hhold'].tolist() == written['hhold'].tolist()
    assert read['wp'].tolist() == written['wp'].tolist()
    assert read['htype'].tolist() == written['htype'].astype(int).tolist()
    assert read['urban'].tolist() == written['urban'].tolist()
    assert read.geometry.geom_equals(written.geometry).all()
    assert (read['long'] == read.geometry.x).all() and (read['lat'] == read.geometry.y).all()
    # attribute-only read (used by the network driver) skips geometry
    attrs = read_population(tmp_path / 'ut_population.gpkg', columns=['id', 'age', 'hhold', 'wp'])
    assert list(attrs.columns) == ['id', 'age', 'hhold', 'wp']


def test_county_run_prefers_its_own_file(tmp_path):
    ut = tmp_path / 'ut'
    _population_gpkg(ut / 'ut_population.gpkg', TRACTS)
    assert population_source(tmp_path, '49', ['035']) == (str(ut / 'ut_population.gpkg'), 'ut')
    _population_gpkg(ut / 'ut_c035_population.gpkg', TRACTS[:1])
    assert population_source(tmp_path, '49', ['035']) == (str(ut / 'ut_c035_population.gpkg'), 'ut_c035')


def test_missing_population_mentions_legacy_pickle(tmp_path):
    (tmp_path / 'ut_population.pickle').write_bytes(b'')
    with pytest.raises(FileNotFoundError, match='legacy'):
        read_population(tmp_path / 'ut_population.gpkg')


@pytest.mark.parametrize('geo,tracts,run', [
    (['--state', 'ut'], TRACTS, 'ut'),
    (['--state', 'ut', '--counties', '035'], TRACTS[:2], 'ut_c035'),
])
def test_synthesis_to_networks_to_validation(data_dir, geo, tracts, run):
    results = data_dir / 'results-data'
    population = gpd.read_file(results / 'ut' / 'ut_population.gpkg')
    population = population[population['id'].str[:11].isin(tracts)].set_index('id')

    # household + education networks, then the work network
    _run(NETWORKS / 'create_edu_hhold_get_work_pop.py', data_dir, *geo)
    _run(NETWORKS / 'create_work_networks.py', data_dir, *geo)

    nets = results / 'ut' / 'social_networks'
    household = _network(nets / f'{run}_household_network.csv')
    assert set(household) == set(population.index)
    for person, ties in household.items():
        hh = population.loc[person, 'hhold']
        assert set(ties) == set(population.index[population.hhold == hh]) - {person}
    for kind, letter in [('school', 's'), ('daycare', 'd')]:
        net = _network(nets / f'{run}_{kind}_network.csv')
        assert set(net) == set(population.index[population.wp.str.contains(letter)])
        for person, ties in net.items():
            assert all(population.loc[t, 'wp'] == population.loc[person, 'wp'] for t in ties)

    workers = population[(population.age >= 18) & population.wp.str.contains('w')]
    work_pop = pd.read_csv(results / '1-us' / f'{run}_work_population.csv', dtype=str)
    assert set(work_pop['id']) == set(workers.index)
    work = _network(results / '1-us' / f'{run}_work_network.csv')
    assert set(work) == set(workers.index)
    for person, ties in work.items():
        assert all(workers.loc[t, 'wp'] == workers.loc[person, 'wp'] for t in ties)

    # validation against the census, restricted to the same geography
    _run(VALIDATION / 'validation_population.py', data_dir, *geo)
    age = pd.read_csv(results / 'ut' / f'{run}_age_verification.csv')
    assert age['SPop_Male'].sum() == (population.gender == 'm').sum() == 18 * PER_GROUP * len(tracts)
    assert age['Good_Census_Male'].sum() == 18 * PER_GROUP * len(tracts)          # failed tract dropped
    assert age['Census_Male'].sum() == 18 * PER_GROUP * (len(tracts) + 1)         # failed tract is in 035
    assert (results / 'ut' / f'{run}_age_ver_plot.png').exists()

    _run(VALIDATION / 'validation_hhold.py', data_dir, *geo)
    hh = pd.read_csv(results / 'ut' / f'{run}_hhold_verification.csv', index_col=0)
    expected = population.drop_duplicates('hhold').htype.astype(int).value_counts()
    assert hh['Spop_hhold'].tolist() == [int(expected.get(t, 0)) for t in range(11)]
    assert hh['Census_hhold'].tolist()[:2] == [2 * (len(tracts) + 1), len(tracts) + 1]
    assert hh['Goodcensus_hhold'].tolist()[:2] == [2 * len(tracts), len(tracts)]
    assert (results / '1-us' / f'{run}_hhold_ver_df.csv').exists()

    _run(VALIDATION / 'validation_tract_avg_hhold.py', data_dir, *geo)
    avg = pd.read_csv(results / 'ut' / f'{run}_avg_hhold_verification.csv', dtype={'tract': str})
    assert sorted(avg['tract']) == tracts
    assert (results / '1-us' / f'{run}_avg_hhold_size_df.csv').exists()


def test_county_run_file_used_when_present(data_dir):
    """A real county run (ut_c035_population.gpkg) wins over filtering the state file."""
    results = data_dir / 'results-data'
    _population_gpkg(results / 'ut' / 'ut_c035_population.gpkg', TRACTS[:1])
    _run(NETWORKS / 'create_edu_hhold_get_work_pop.py', data_dir, '--state', 'ut', '--counties', '035')
    household = _network(results / 'ut' / 'social_networks' / 'ut_c035_household_network.csv')
    assert {p[:11] for p in household} == {TRACTS[0]}
    _run(VALIDATION / 'validation_population.py', data_dir, '--state', 'ut', '--counties', '035')
    age = pd.read_csv(results / 'ut' / 'ut_c035_age_verification.csv')
    assert age['SPop_Male'].sum() == 18 * PER_GROUP


COSINE_AGG = """
import importlib.util, sys
import pandas as pd
spec = importlib.util.spec_from_file_location('cosine', sys.argv[1])
cosine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cosine)
rel = pd.DataFrame({'GEOID': sys.argv[2:], 'PUMAID': ['4900001', '4900001', '4900002']})
agg = cosine.get_us_aggregate_spop_data(rel, ['49'], ['035'])
print(list(agg.index), int(agg.to_numpy().sum()))
"""


def test_external_validation_reads_gpkg(data_dir):
    """Both external-validation scripts load the GeoPackage (formerly a .pickle) for the run."""
    results = data_dir / 'results-data'

    # Spearman block-group check: two block groups per tract (halves of the tract box)
    rows = []
    for i, geoid in enumerate(TRACTS):
        minx = -112 + i * 0.01
        for j, (x0, x1) in enumerate([(minx, minx + 0.002), (minx + 0.002, minx + 0.01)]):
            rows.append({'STATEFP': '49', 'GEOID20': f'{geoid}{j + 1}', 'tract': geoid, 'urban': 1,
                         'B01001e1': 10 * (j + 1), 'geometry': box(x0, 40.7, x1, 40.71)})
    acs = data_dir / 'processed-data' / 'acs'
    acs.mkdir(parents=True)
    gpd.GeoDataFrame(rows, crs='EPSG:4269').to_file(acs / 'acs_bg_boundary_population.gpkg', driver='GPKG')
    _run(VALIDATION / 'validation_external_sc_bg.py', data_dir, '--state', 'ut', '--counties', '035')
    spc = pd.read_csv(results / 'ut' / 'ut_c035_spc_tract.csv', dtype={'tract': str})
    assert sorted(spc['tract']) == TRACTS[:2]
    summary = pd.read_csv(results / '1-us' / 'ut_c035_state_spearman_correlation.csv')
    assert summary['all'].tolist() == [2]

    # PUMA cosine check: the synthetic aggregation step (PUMS microdata are not in the repo)
    env = dict(os.environ, GSPN_DATA_DIR=str(data_dir), PYTHONPATH=str(ROOT))
    result = subprocess.run([sys.executable, '-c', COSINE_AGG, str(VALIDATION / 'validation_external_cosine.py'),
                             *TRACTS], env=env, capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stderr[-3000:]
    assert result.stdout.split('\n')[-2] == f"['4900001'] {36 * PER_GROUP * 2}"
