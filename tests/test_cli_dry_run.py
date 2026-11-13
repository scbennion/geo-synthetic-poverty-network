import os
import subprocess
import sys
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import box

ROOT = Path(__file__).resolve().parent.parent
SYNTH = 'pipeline.population_synthesis.run_synthesis_by_state'

CLI_MODULES = [
    'pipeline.preprocess.prepare_census.download_census_inputs',
    'pipeline.preprocess.prepare_census.process_census_shp',
    'pipeline.preprocess.prepare_commute.process_lodes8',
    'pipeline.preprocess.prepare_commute.process_cbp',
    'pipeline.preprocess.prepare_commute.add_tract_workplaces',
    'pipeline.preprocess.prepare_commute.build_tract_workplace_json',
    'pipeline.preprocess.prepare_roads.download_process_roads',
    'pipeline.preprocess.prepare_roads.clean_roads',
    'pipeline.preprocess.prepare_education.build_edu_sites',
    'pipeline.population_synthesis.run_synthesis_by_state',
    'pipeline.social_networks.create_edu_hhold_get_work_pop',
    'pipeline.social_networks.create_work_networks',
    'pipeline.validation.validation_population',
    'pipeline.validation.validation_hhold',
    'pipeline.validation.validation_tract_avg_hhold',
    'pipeline.validation.validation_external_cosine',
    'pipeline.validation.validation_external_sc_bg',
    'pipeline.knowledge_graph.export_neo4j_csv',
]


@pytest.mark.parametrize('module', CLI_MODULES)
def test_cli_help_without_pythonpath(module, tmp_path):
    env = dict(os.environ, GSPN_DATA_DIR=str(tmp_path / 'data'))
    env.pop('PYTHONPATH', None)
    result = subprocess.run([sys.executable, '-m', module, '--help'], cwd=ROOT, env=env,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert 'usage:' in result.stdout
    assert not (tmp_path / 'data').exists()

# two Salt Lake (035) tracts, one Utah County (049) tract, one empty tract
TRACTS = {'49035100100': 10, '49035100200': 20, '49049000100': 30, '49035999999': 0}


def _write_fixture(data_dir):
    census = data_dir / 'processed-data' / 'census'
    census.mkdir(parents=True)
    gdf = gpd.GeoDataFrame(
        {'GEOID': list(TRACTS), 'DP1_0001C': list(TRACTS.values())},
        geometry=[box(i, 0, i + 1, 1) for i in range(len(TRACTS))], crs='EPSG:4269')
    gdf.to_file(census / 'ut-tracts-demo-work.shp.zip', driver='ESRI Shapefile')


def _dry_run(tmp_path, *args):
    _write_fixture(tmp_path)
    env = dict(os.environ, GSPN_DATA_DIR=str(tmp_path))
    env.pop('PYTHONPATH', None)
    return subprocess.run([sys.executable, '-m', SYNTH, '--dry-run', *args],
                          cwd=ROOT, env=env, capture_output=True, text=True)


def test_dry_run_one_county(tmp_path):
    result = _dry_run(tmp_path, '--state', 'ut', '--counties', '035')
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ['49035100100', '49035100200']
    assert not (tmp_path / 'results-data').exists()


def test_dry_run_whole_state(tmp_path):
    result = _dry_run(tmp_path, '--state', 'ut')
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ['49035100100', '49035100200', '49049000100']


def test_counties_without_state_rejected(tmp_path):
    result = _dry_run(tmp_path, '--counties', '035')
    assert result.returncode != 0
