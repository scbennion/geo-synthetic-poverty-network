import importlib
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

import src.settings as settings
from src.command_line_options import parse_counties, resolve_state_codes

ROOT = Path(__file__).resolve().parents[1]
MODULES = sorted(
    '.'.join(p.relative_to(ROOT).with_suffix('').parts)
    for package in ('src', 'pipeline') for p in (ROOT / package).rglob('*.py')
    if p.stem != '__init__'
)
# needs a GRASS GIS install, which is not a Python package
OPTIONAL = {'grass', 'grass_session'}


@pytest.mark.parametrize('name', MODULES)
def test_module_imports(name):
    try:
        importlib.import_module(name)
    except ModuleNotFoundError as e:
        if e.name.split('.')[0] in OPTIONAL:
            pytest.skip(f'optional dependency missing: {e.name}')
        raise


def test_wheel_includes_pipeline_and_shared_modules(tmp_path):
    """Installed modules work outside the checkout, without stage path overrides."""
    root = Path(__file__).resolve().parents[1]
    project, wheels, installed = tmp_path / 'project', tmp_path / 'wheels', tmp_path / 'installed'
    project.mkdir()
    for directory in ('src', 'pipeline'):
        shutil.copytree(root / directory, project / directory,
                        ignore=shutil.ignore_patterns('__pycache__'))
    for filename in ('pyproject.toml', 'LICENSE'):
        shutil.copy2(root / filename, project / filename)
    result = subprocess.run([
        sys.executable, '-m', 'pip', 'wheel', '--no-deps', '--no-build-isolation',
        '--no-index', '--no-cache-dir', '--wheel-dir', str(wheels), str(project),
    ], cwd=tmp_path, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    with zipfile.ZipFile(next(wheels.glob('*.whl'))) as wheel:
        assert all(name.startswith(('src/', 'pipeline/', 'geo_synthetic_poverty_network-'))
                   for name in wheel.namelist())
        for name in MODULES:
            assert name.replace('.', '/') + '.py' in wheel.namelist()
        for filename in ('constraints.cypher', 'tract_summary.cypher'):
            assert f'pipeline/knowledge_graph/{filename}' in wheel.namelist()
        wheel.extractall(installed)
    env = dict(os.environ, GSPN_DATA_DIR=str(tmp_path / 'data'))
    env.pop('PYTHONPATH', None)
    result = subprocess.run([
        sys.executable, '-c',
        'import importlib; from pathlib import Path; '
        f'modules = [importlib.import_module(name) for name in {MODULES!r}]; '
        f'assert all(Path(module.__file__).is_relative_to({str(installed)!r}) for module in modules)',
    ], cwd=installed, env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    result = subprocess.run([
        sys.executable, '-m', 'pipeline.preprocess.prepare_census.download_census_inputs', '--help',
    ], cwd=installed, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


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
    from src.command_line_options import run_name, us_run_name
    assert run_name('ut') == 'ut'
    assert run_name('ut', ['049', '035']) == 'ut_c035-049'
    assert us_run_name(settings.state_codes) == 'us'
    assert us_run_name(['49']) == 'ut'
    assert us_run_name(['49'], ['035']) == 'ut_c035'
