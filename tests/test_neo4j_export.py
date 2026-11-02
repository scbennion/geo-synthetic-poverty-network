import csv
import importlib.util
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('export_neo4j_csv', ROOT / 'code' / '4-knowledge-graph' / 'export_neo4j_csv.py')
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)

T = '49035100100'
PEOPLE = [  # id, age, hhold, htype, wp
    (f'{T}i0', 40.0, f'{T}h0', 1.0, f'{T}w0'),
    (f'{T}i1', 38.0, f'{T}h0', 1.0, f'{T}h0'),          # adult without a job
    (f'{T}i2', 8.0, f'{T}h0', 1.0, '49s001'),
    (f'{T}i3', 2.0, f'{T}h0', 1.0, '49d001'),
    (f'{T}i4', 30.0, f'{T}h1', 4.0, '49049000100w5'),   # works outside the county
    (f'{T}i5', 50.0, f'{T}h2', 0.0, '49045000100wNone'),
]


def _write_run(results, name='ut_c035'):
    st = results / 'ut'
    (st / 'social_networks').mkdir(parents=True)
    (results / '1-us').mkdir()
    pop = pd.DataFrame([{'id': i, 'age': a, 'gender': 'f', 'assigned': 1, 'hhold': h, 'htype': ht,
                         'geometry': 'POINT (-111.9 40.7)', 'wp': wp, 'urban': True,
                         'long': -111.9 + n / 100, 'lat': 40.7} for n, (i, a, h, ht, wp) in enumerate(PEOPLE)])
    # one home point per household, as synthesis writes it
    pop[['long', 'lat']] = pop.groupby('hhold')[['long', 'lat']].transform('first')
    pop.to_csv(st / f'{name}_population.csv')
    with sqlite3.connect(st / f'{name}_workplace.gpkg') as con:
        con.execute(f'CREATE TABLE {name}_workplace (fid INTEGER PRIMARY KEY, geom BLOB, wp TEXT, long REAL, lat REAL)')
        con.executemany(f'INSERT INTO {name}_workplace (wp, long, lat) VALUES (?, ?, ?)',
                        [(f'{T}w0', -111.8, 40.6), (f'{T}w1', -111.81, 40.61)])
    adj = {  # adjacency rows list both directions, as create_social_networks.to_csv writes them
        st / 'social_networks' / f'{name}_household_network.csv':
            [[f'{T}i{a}'] + [f'{T}i{b}' for b in range(4) if b != a] for a in range(4)] + [[f'{T}i4'], [f'{T}i5']],
        st / 'social_networks' / f'{name}_school_network.csv': [[f'{T}i2']],
        st / 'social_networks' / f'{name}_daycare_network.csv': [[f'{T}i3']],
        results / '1-us' / f'{name}_work_network.csv': [[f'{T}i0', f'{T}i4'], [f'{T}i4', f'{T}i0'], [f'{T}i5']],
    }
    for path, rows in adj.items():
        with open(path, 'w', newline='') as f:
            csv.writer(f).writerows(rows)


def _read(out, name):
    return pd.read_csv(out / name, dtype=str, keep_default_na=False)


def test_export_nodes_and_relationships(tmp_path, monkeypatch):
    _write_run(tmp_path / 'results')
    monkeypatch.setattr(exporter, 'RESULTS_DIR', str(tmp_path / 'results'))
    out = tmp_path / 'out'
    args = exporter.export_run('49', ['035'], str(out), seed=42)

    assert len(_read(out, 'persons.csv')) == 6
    hh = _read(out, 'households.csv').set_index('id:ID(Household)')
    assert hh.loc[f'{T}h0', 'size:int'] == '4' and hh.loc[f'{T}h0', 'htype:int'] == '1'

    wp = _read(out, 'workplaces.csv').set_index('id:ID(Workplace)')
    assert set(wp.index) == {f'{T}w0', f'{T}w1', '49049000100w5', '49045000100wNone'}
    assert wp.loc[f'{T}w0', 'location:point{crs:WGS-84}'].startswith('{longitude:-111.8')
    assert wp.loc['49049000100w5', 'location:point{crs:WGS-84}'] == ''      # outside the county: no point
    assert wp.loc['49045000100wNone', 'placeholder:boolean'] == 'true'

    works = _read(out, 'works_at.csv')
    assert sorted(works[':START_ID(Person)']) == [f'{T}i0', f'{T}i4', f'{T}i5']   # not the jobless adult
    assert list(_read(out, 'attends_school.csv')[':END_ID(School)']) == ['49s001']
    assert list(_read(out, 'attends_daycare.csv')[':END_ID(Daycare)']) == ['49d001']
    assert set(_read(out, 'tract_in_county.csv')[':END_ID(County)']) == {'49035', '49049', '49045'}

    # each undirected contact is written once
    assert len(_read(out, 'contact_household.csv')) == 6
    assert _read(out, 'contact_work.csv').values.tolist() == [[f'{T}i0', f'{T}i4', 'work']]
    assert len(_read(out, 'contact_school.csv')) == 0

    run = _read(out, 'run.csv').iloc[0]
    assert run['name:ID(Run)'] == 'ut_c035' and run['seed:int'] == '42'

    lines = Path(args).read_text().splitlines()
    assert f'--nodes=Person={out / "persons.csv"}' in lines
    assert sum(line.startswith('--relationships=CONTACT=') for line in lines) == 4


def test_contact_outside_population_raises(tmp_path, monkeypatch):
    _write_run(tmp_path / 'results')
    with open(tmp_path / 'results' / '1-us' / 'ut_c035_work_network.csv', 'a', newline='') as f:
        csv.writer(f).writerow([f'{T}i0', f'{T}i99'])
    monkeypatch.setattr(exporter, 'RESULTS_DIR', str(tmp_path / 'results'))
    with pytest.raises(ValueError, match='i99'):
        exporter.export_run('49', ['035'], str(tmp_path / 'out'))
