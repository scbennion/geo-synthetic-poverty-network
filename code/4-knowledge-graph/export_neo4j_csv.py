"""Export one synthesis run to CSV files for a Neo4j bulk import (neo4j-admin database import).

Reads the run's outputs under RESULTS_DIR:
  <state>/<run>_population.csv, <state>/<run>_workplace.gpkg,
  <state>/social_networks/<run>_{household,school,daycare}_network.csv,
  1-us/<run>_work_network.csv
and writes <DATA_DIR>/neo4j-import/<run>/ with one CSV per node label and relationship type,
plus import.args (the neo4j-admin argument file). The graph model is in docs/knowledge-graph.md.

Run: python export_neo4j_csv.py --state ut --counties 035
"""
import argparse
import csv
import os
import sqlite3
import subprocess
from datetime import datetime, timezone

import pandas as pd
from loguru import logger
from src.cli import add_geography_args, resolve_geography, run_name
from src.settings import DATA_DIR, PROJECT_ROOT, RESULTS_DIR, state_dict

SETTINGS = ('household', 'school', 'daycare', 'work')


def site_kind(wp):
    """'w' work, 's' school, 'd' daycare, 'h' home (adults without a job), as in create_social_networks.wp_kind."""
    return wp.astype(str).str.extract(r'^\d*([a-z])', expand=False)


def point(long, lat):
    return '{longitude:' + repr(float(long)) + ',latitude:' + repr(float(lat)) + '}'


def read_contacts(path, people):
    """Undirected edges from a network file (one line per person: the person, then every neighbour)."""
    edges = set()
    with open(path, newline='') as f:
        for row in csv.reader(f):
            a = row[0]
            for b in row[1:]:
                edges.add((a, b) if a < b else (b, a))
    unknown = {p for e in edges for p in e} - people
    if unknown:
        raise ValueError(f"{path}: {len(unknown)} people not in the population, e.g. {sorted(unknown)[:3]}")
    return sorted(edges)


def read_workplaces(path):
    table = os.path.splitext(os.path.basename(path))[0]
    with sqlite3.connect(f'file:{path}?mode=ro', uri=True) as con:
        return pd.read_sql(f'SELECT wp AS id, long, lat FROM "{table}"', con)


def git_commit():
    try:
        return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=PROJECT_ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ''


def export_run(state_code, counties, out_dir, seed=None):
    st = state_dict[state_code].lower()
    name = run_name(st, counties)
    state_dir = os.path.join(RESULTS_DIR, st)
    os.makedirs(out_dir, exist_ok=True)
    files = []  # (kind, label or type, filename)

    def write(df, filename, kind, label):
        df.to_csv(os.path.join(out_dir, filename), index=False)
        files.append((kind, label, filename))
        logger.info(f"{label}: {len(df):,} -> {filename}")

    pop = pd.read_csv(os.path.join(state_dir, f'{name}_population.csv'), index_col=0,
                      dtype={'id': str, 'hhold': str, 'wp': str})
    people = set(pop['id'])
    kind = site_kind(pop['wp'])

    # ---- nodes
    write(pd.DataFrame({'id:ID(Person)': pop['id'], 'age:int': pop['age'].astype(int),
                        'gender': pop['gender']}), 'persons.csv', 'nodes', 'Person')

    hh = pop.groupby('hhold').agg(htype=('htype', 'first'), size=('id', 'size'), urban=('urban', 'first'),
                                  long=('long', 'first'), lat=('lat', 'first')).reset_index()
    write(pd.DataFrame({'id:ID(Household)': hh['hhold'], 'htype:int': hh['htype'].astype(int),
                        'size:int': hh['size'], 'urban:boolean': hh['urban'].map({True: 'true', False: 'false'}),
                        'location:point{crs:WGS-84}': [point(x, y) for x, y in zip(hh['long'], hh['lat'])]}),
          'households.csv', 'nodes', 'Household')

    wp_points = read_workplaces(os.path.join(state_dir, f'{name}_workplace.gpkg')).set_index('id')
    wp_ids = sorted(set(wp_points.index) | set(pop.loc[kind == 'w', 'wp']))
    wps = pd.DataFrame({'id': wp_ids}).join(wp_points, on='id')
    write(pd.DataFrame({'id:ID(Workplace)': wps['id'],
                        'placeholder:boolean': wps['id'].str.endswith('wNone').map({True: 'true', False: 'false'}),
                        'location:point{crs:WGS-84}': [point(x, y) if pd.notna(x) else ''
                                                       for x, y in zip(wps['long'], wps['lat'])]}),
          'workplaces.csv', 'nodes', 'Workplace')

    for k, label in (('s', 'School'), ('d', 'Daycare')):
        enrolled = pop.loc[kind == k, 'wp'].value_counts().sort_index()
        write(pd.DataFrame({f'id:ID({label})': enrolled.index, 'enrolled:int': enrolled.values}),
              f'{label.lower()}s.csv', 'nodes', label)

    tracts = sorted(set(hh['hhold'].str[:11]) | set(wps['id'].str[:11]))
    county_ids = sorted({t[:5] for t in tracts})
    write(pd.DataFrame({'geoid:ID(Tract)': tracts}), 'tracts.csv', 'nodes', 'Tract')
    write(pd.DataFrame({'fips:ID(County)': county_ids}), 'counties.csv', 'nodes', 'County')
    state_ids = sorted({c[:2] for c in county_ids})
    write(pd.DataFrame({'fips:ID(State)': state_ids, 'abbreviation': [state_dict[s] for s in state_ids]}),
          'states.csv', 'nodes', 'State')

    write(pd.DataFrame([{'name:ID(Run)': name, 'state': st, 'counties:string[]': ';'.join(counties or []),
                         'seed:int': '' if seed is None else seed, 'export_commit': git_commit(),
                         'exported_at': datetime.now(timezone.utc).isoformat(timespec='seconds')}]),
          'run.csv', 'nodes', 'Run')

    # ---- relationships
    write(pd.DataFrame({':START_ID(Person)': pop['id'], ':END_ID(Household)': pop['hhold']}),
          'member_of.csv', 'relationships', 'MEMBER_OF')
    write(pd.DataFrame({':START_ID(Household)': hh['hhold'], ':END_ID(Tract)': hh['hhold'].str[:11]}),
          'household_in_tract.csv', 'relationships', 'IN_TRACT')
    write(pd.DataFrame({':START_ID(Workplace)': wps['id'], ':END_ID(Tract)': wps['id'].str[:11]}),
          'workplace_in_tract.csv', 'relationships', 'IN_TRACT')
    write(pd.DataFrame({':START_ID(Tract)': tracts, ':END_ID(County)': [t[:5] for t in tracts]}),
          'tract_in_county.csv', 'relationships', 'IN_COUNTY')
    write(pd.DataFrame({':START_ID(County)': county_ids, ':END_ID(State)': [c[:2] for c in county_ids]}),
          'county_in_state.csv', 'relationships', 'IN_STATE')

    workers = pop[kind == 'w']
    write(pd.DataFrame({':START_ID(Person)': workers['id'], ':END_ID(Workplace)': workers['wp']}),
          'works_at.csv', 'relationships', 'WORKS_AT')
    for k, label in (('s', 'School'), ('d', 'Daycare')):
        kids = pop[kind == k]
        write(pd.DataFrame({':START_ID(Person)': kids['id'], f':END_ID({label})': kids['wp']}),
              f'attends_{label.lower()}.csv', 'relationships', 'ATTENDS')

    network_paths = {s: os.path.join(state_dir, 'social_networks', f'{name}_{s}_network.csv')
                     for s in ('household', 'school', 'daycare')}
    network_paths['work'] = os.path.join(RESULTS_DIR, '1-us', f'{name}_work_network.csv')
    for setting in SETTINGS:
        edges = read_contacts(network_paths[setting], people)
        write(pd.DataFrame({':START_ID(Person)': [a for a, _ in edges], ':END_ID(Person)': [b for _, b in edges],
                            'setting': setting}), f'contact_{setting}.csv', 'relationships', 'CONTACT')

    args_path = os.path.join(out_dir, 'import.args')
    with open(args_path, 'w') as f:
        for kind_, label, filename in files:
            f.write(f'--{kind_}={label}={os.path.abspath(os.path.join(out_dir, filename))}\n')
    logger.info(f"neo4j-admin argument file: {args_path}")
    return args_path


def main(argv=None):
    parser = add_geography_args(argparse.ArgumentParser(description=__doc__.split('\n\n')[0]))
    parser.add_argument('--seed', type=int, default=None, help='seed the run was made with (recorded on the Run node)')
    parser.add_argument('--output', default=None, help='output folder (default: DATA_DIR/neo4j-import/<run>)')
    args = parser.parse_args(argv)
    try:
        codes, counties = resolve_geography(args)
    except argparse.ArgumentTypeError as e:
        parser.error(str(e))
    if len(codes) != 1:
        parser.error('--state is required: export one run at a time')
    name = run_name(state_dict[codes[0]].lower(), counties)
    export_run(codes[0], counties, args.output or os.path.join(DATA_DIR, 'neo4j-import', name), args.seed)


if __name__ == '__main__':
    main()
