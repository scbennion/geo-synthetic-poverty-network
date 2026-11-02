import importlib
import os
from pathlib import Path

import pytest

import src.settings as settings
from src.cli import parse_counties, resolve_state_codes

SRC_MODULES = sorted(p.stem for p in Path(settings.__file__).parent.glob('*.py') if p.stem != '__init__')
# needs a GRASS GIS install, which is not a Python package
OPTIONAL = {'grass', 'grass_session'}


@pytest.mark.parametrize('name', SRC_MODULES)
def test_src_module_imports(name):
    try:
        importlib.import_module(f'src.{name}')
    except ModuleNotFoundError as e:
        if e.name.split('.')[0] in OPTIONAL:
            pytest.skip(f'optional dependency missing: {e.name}')
        raise


def test_settings_dirs_share_data_dir():
    for d in (settings.RAW_DATA_DIR, settings.INTERIM_DATA_DIR,
              settings.PROCESSED_DATA_DIR, settings.RESULTS_DIR):
        assert os.path.dirname(d) == settings.DATA_DIR


def test_data_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv('GSPN_DATA_DIR', str(tmp_path))
    reloaded = importlib.reload(settings)
    try:
        assert reloaded.RESULTS_DIR == os.path.join(str(tmp_path), 'results-data')
    finally:
        monkeypatch.delenv('GSPN_DATA_DIR')
        importlib.reload(settings)


def test_state_and_county_parsing():
    assert resolve_state_codes('ut') == ['49']
    assert resolve_state_codes('49') == ['49']
    assert len(resolve_state_codes(None)) == 51
    assert parse_counties('035,49') == ['035', '049']
    assert parse_counties(None) is None


def test_run_names():
    from src.cli import run_name, us_run_name
    assert run_name('ut') == 'ut'
    assert run_name('ut', ['049', '035']) == 'ut_c035-049'
    assert us_run_name(settings.state_codes) == 'us'
    assert us_run_name(['49']) == 'ut'
    assert us_run_name(['49'], ['035']) == 'ut_c035'
