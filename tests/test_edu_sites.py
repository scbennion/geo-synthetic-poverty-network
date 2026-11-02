"""Tests for code/0-preprocess/prepare-edu/build_edu_sites.py on small synthetic raw layers (no network)."""
import importlib.util
import os
import random
import subprocess
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, box

from src.assign_education_site import __assign_education_site__

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / 'code' / '0-preprocess' / 'prepare-edu' / 'build_edu_sites.py'
REQUIRED = ['eduID', 'geometry', 'LATITUDE', 'LONGITUDE', 's_age', 'e_age', 'ENROLLMENT', 'count']


def _load_module():
    spec = importlib.util.spec_from_file_location('build_edu_sites', SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bes = _load_module()


def _layer(rows, id_col):
    df = pd.DataFrame(rows)
    df[id_col] = df[id_col].astype(str)
    for col in ('ENROLLMENT', 'POPULATION'):  # int32 in the source FileGDB
        if col in df:
            df[col] = df[col].astype('int32')
    return gpd.GeoDataFrame(df, geometry=[Point(x, y) for x, y in zip(df.LONGITUDE, df.LATITUDE)],
                            crs='EPSG:4326')


def _raw_layers():
    # Salt Lake City area; one Nevada record per layer must be filtered out
    public = _layer([
        dict(NCESID='490000100001', NAME='PRIMARY A', STATE='UT', LEVEL='Primary', ENROLLMENT=500,
             POPULATION=530, LATITUDE=40.760, LONGITUDE=-111.890),
        dict(NCESID='490000100002', NAME='MIDDLE B', STATE='UT', LEVEL='Middle', ENROLLMENT=800,
             POPULATION=840, LATITUDE=40.765, LONGITUDE=-111.885),
        dict(NCESID='490000100003', NAME='HIGH C', STATE='UT', LEVEL='High', ENROLLMENT=1500,
             POPULATION=1580, LATITUDE=40.755, LONGITUDE=-111.895),
        dict(NCESID='490000100004', NAME='CLOSED D', STATE='UT', LEVEL='Other', ENROLLMENT=-9,
             POPULATION=0, LATITUDE=40.770, LONGITUDE=-111.880),
        dict(NCESID='320000100001', NAME='NEVADA E', STATE='NV', LEVEL='Primary', ENROLLMENT=300,
             POPULATION=320, LATITUDE=36.17, LONGITUDE=-115.14),
    ], 'NCESID')
    private = _layer([
        dict(NCESID='A1234567', NAME='PRIVATE ELEM', STATE='UT', LEVEL='Elementary', ENROLLMENT=40,
             POPULATION=45, LATITUDE=40.762, LONGITUDE=-111.892),
        dict(NCESID='A7654321', NAME='PRIVATE SEC', STATE='UT', LEVEL='Secondary', ENROLLMENT=-1,
             POPULATION=60, LATITUDE=40.758, LONGITUDE=-111.888),
        dict(NCESID='K0000001', NAME='PRIVATE NV', STATE='NV', LEVEL='Secondary', ENROLLMENT=10,
             POPULATION=12, LATITUDE=36.18, LONGITUDE=-115.15),
    ], 'NCESID')
    daycare = _layer([
        dict(ID='0000000001', NAME='Daycare One', STATE='UT', POPULATION=80, LATITUDE=40.761, LONGITUDE=-111.891),
        dict(ID='0000000002', NAME='Daycare Two', STATE='UT', POPULATION=120, LATITUDE=40.759, LONGITUDE=-111.889),
        dict(ID='0000000003', NAME='Daycare NV', STATE='NV', POPULATION=50, LATITUDE=36.17, LONGITUDE=-115.14),
    ], 'ID')
    return {'PublicSchools': public, 'PrivateSchools': private, 'DayCareCenters': daycare}


def _write_epa_zip(path):
    """Mimic ORNL_Education.zip: a zip with a FileGDB 'Education.gdb' holding the source layers."""
    gdb = path.parent / 'build' / 'Education.gdb'
    gdb.parent.mkdir(parents=True)
    for name, gdf in _raw_layers().items():
        gdf.to_file(gdb, layer=name, driver='OpenFileGDB')
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, 'w') as z:
        for f in sorted(gdb.iterdir()):
            z.write(f, f"Education.gdb/{f.name}")
    return path


@pytest.fixture
def built(tmp_path):
    raw = _write_epa_zip(tmp_path / 'raw' / 'ORNL_Education.zip')
    out = tmp_path / 'edu'
    paths = bes.build_epa2015('49', raw_path=str(raw), out_dir=str(out))
    return {k: gpd.read_file(v) for k, v in paths.items()}


def test_outputs_have_assignment_fields(built):
    for kind, gdf in built.items():
        assert set(REQUIRED) <= set(gdf.columns), kind
        assert gdf.crs.to_epsg() == 4269
        assert gdf['eduID'].notna().all() and gdf['eduID'].is_unique
        assert pd.api.types.is_integer_dtype(gdf['ENROLLMENT'])
        assert (gdf['ENROLLMENT'] >= 0).all()
        assert pd.api.types.is_integer_dtype(gdf['count']) and (gdf['count'] == 0).all()
        assert (gdf['LONGITUDE'] == gdf.geometry.x).all() and (gdf['LATITUDE'] == gdf.geometry.y).all()


def test_state_filter_and_layer_mapping(built):
    school, daycare = built['school'], built['daycare']
    assert len(school) == 6 and len(daycare) == 2  # Nevada records dropped
    assert set(school['SRC_LAYER']) == {'PublicSchools', 'PrivateSchools'}
    assert set(daycare['SRC_LAYER']) == {'DayCareCenters'}


def test_eduid_markers_match_network_selection(built):
    # create_social_networks selects school/daycare/work members by 's'/'d'/'w' in wp
    for eid in built['school']['eduID']:
        assert eid.startswith('49s') and 'd' not in eid and 'w' not in eid
    for eid in built['daycare']['eduID']:
        assert eid.startswith('49d') and 's' not in eid and 'w' not in eid


def test_age_bands_from_existing_helpers(built):
    bands = built['school'].set_index('NAME')[['s_age', 'e_age']].apply(tuple, axis=1).to_dict()
    assert bands == {'PRIMARY A': (5, 11), 'MIDDLE B': (12, 14), 'HIGH C': (15, 17), 'CLOSED D': (5, 17),
                     'PRIVATE ELEM': (5, 11), 'PRIVATE SEC': (12, 17)}
    assert (built['daycare']['s_age'] == 0).all() and (built['daycare']['e_age'] == 4).all()


def test_negative_enrollment_codes_become_zero(built):
    school = built['school'].set_index('NAME')
    assert school.loc['CLOSED D', 'ENROLLMENT'] == 0 and school.loc['CLOSED D', 'ENROLLMENT_SRC'] == -9
    assert school.loc['PRIVATE SEC', 'ENROLLMENT'] == 0 and bool(school.loc['PRIVATE SEC', 'ENR_MISSING'])
    assert school.loc['HIGH C', 'ENROLLMENT'] == 1500 and not bool(school.loc['HIGH C', 'ENR_MISSING'])


def test_clean_enrollment_handles_null_and_float():
    enrollment, src, missing = bes._clean_enrollment(pd.Series([12.0, None, -2.0, 0.0]))
    assert enrollment.tolist() == [12, 0, 0, 0] and pd.api.types.is_integer_dtype(enrollment)
    assert missing.tolist() == [False, True, True, False]
    assert src.isna().tolist() == [False, True, False, False]


def test_daycare_enrollment_from_population(built):
    assert sorted(built['daycare']['ENROLLMENT']) == [80, 120]


def test_deterministic_ids(tmp_path, built):
    raw = _write_epa_zip(tmp_path / 'raw2' / 'ORNL_Education.zip')
    again = bes.build_school(str(raw), '49')
    assert again['eduID'].tolist() == built['school']['eduID'].tolist()
    assert again['SRC_ID'].tolist() == built['school']['SRC_ID'].tolist()


def test_outputs_work_with_assignment_module(built):
    random.seed(0)
    tract = pd.Series({'geometry': box(-111.90, 40.75, -111.88, 40.77)}, name='49035000100')
    people = gpd.GeoDataFrame({'age': [2, 7, 13, 16]}, geometry=[Point(-111.89, 40.76)] * 4, crs='EPSG:4326')
    people['wp'] = None
    __assign_education_site__(tract, people, built['school'], built['daycare'])
    wp = dict(zip(people['age'], people['wp']))
    assert wp[2] in set(built['daycare']['eduID'])
    school = built['school'].set_index('eduID')
    for age in (7, 13, 16):
        assert school.loc[wp[age], 's_age'] <= age <= school.loc[wp[age], 'e_age']


def test_cli_default_paths(tmp_path):
    """Driver reads RAW_DATA_DIR/edu/epa2015/ORNL_Education.zip and writes PROCESSED_DATA_DIR/edu/."""
    _write_epa_zip(tmp_path / 'raw-data' / 'edu' / 'epa2015' / 'ORNL_Education.zip')
    env = dict(os.environ, GSPN_DATA_DIR=str(tmp_path), PYTHONPATH=str(ROOT))
    result = subprocess.run([sys.executable, str(SCRIPT), '--state', 'ut'], env=env,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    for kind in ('school', 'daycare'):
        assert (tmp_path / 'processed-data' / 'edu' / f'ut_{kind}_id.gpkg').exists()


def test_cli_missing_raw_fails_with_hint(tmp_path):
    env = dict(os.environ, GSPN_DATA_DIR=str(tmp_path), PYTHONPATH=str(ROOT))
    result = subprocess.run([sys.executable, str(SCRIPT), '--state', 'ut'], env=env,
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert 'ORNL_Education.zip' in result.stderr and '--download' in result.stderr


def test_nces_ccd_not_implemented(tmp_path):
    with pytest.raises(NotImplementedError, match='nces_ccd'):
        bes.main(['--state', 'ut', '--source', 'nces_ccd', '--out-dir', str(tmp_path)])
