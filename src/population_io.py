"""Reading the synthesis output (``<state>/<run>_population.gpkg``) in later stages.

The synthesis driver writes one GeoPackage per run (see ``src.cli.run_name``):
``results-data/ut/ut_population.gpkg`` for a full-state run and
``results-data/ut/ut_c035_population.gpkg`` for a county run. Its layer holds the
columns built in ``src.tools.__collect_results__``: ``id``, ``age``, ``gender``,
``assigned``, ``hhold``, ``htype``, ``wp``, ``urban``, ``long``, ``lat`` and the
point ``geometry`` (EPSG:4269). The network and validation stages read that file
directly through this module; there is no intermediate ``.pickle``.
"""
import os

import geopandas as gpd
import pandas as pd
from loguru import logger

from src.cli import in_counties, run_name
from src.settings import state_dict

# integer columns as written by the synthesis; coerced back if a reader returns strings
_INT_COLUMNS = ('age', 'htype', 'assigned')


def population_source(results_dir, state_code, counties=None):
    """Return (path, source_name) of the population file for a run.

    A county run reads ``<state>_c<counties>_population.gpkg`` if it exists, otherwise
    the full-state ``<state>_population.gpkg`` (to be filtered to the counties by the
    caller). ``source_name`` is the run prefix of the file actually used, so sibling
    outputs of that synthesis run (e.g. ``<source_name>_error_log.csv``) can be found.
    """
    state_abbreviation = state_dict[state_code].lower()
    name = run_name(state_abbreviation, counties)
    path = os.path.join(results_dir, state_abbreviation, f"{name}_population.gpkg")
    if counties is not None and not os.path.exists(path):
        full = os.path.join(results_dir, state_abbreviation, f"{state_abbreviation}_population.gpkg")
        logger.info(f"No {name} population, filtering {full}")
        return full, state_abbreviation
    return path, name


def read_population(path, columns=None, state_code=None, counties=None):
    """Read a synthesis population GeoPackage.

    :param columns: columns to keep (default: all). Geometry is read only if
        ``'geometry'`` is among them (or ``columns`` is None); otherwise a plain
        DataFrame is returned, which is much faster for state-sized files.
    :param state_code, counties: if ``counties`` is given, keep only people whose
        home tract (the first 11 characters of ``id``) lies in those counties.
    """
    if not os.path.exists(path):
        legacy = os.path.splitext(path)[0] + '.pickle'
        hint = f" (found legacy {legacy}; convert it to GeoPackage first)" if os.path.exists(legacy) else ''
        raise FileNotFoundError(f"population file not found: {path}{hint}")

    want_geometry = columns is None or 'geometry' in columns
    attr_columns = None if columns is None else [c for c in columns if c != 'geometry']
    population = gpd.read_file(path, columns=attr_columns, ignore_geometry=not want_geometry)

    if 'id' in population.columns:
        population['id'] = population['id'].astype(str)
    for col in _INT_COLUMNS:
        if col in population.columns and not pd.api.types.is_numeric_dtype(population[col]):
            population[col] = pd.to_numeric(population[col])

    if counties is not None:
        population = population[in_counties(population['id'], state_code, counties)]
    if columns is not None:
        population = population.loc[:, list(columns)]
    return population


def load_population(results_dir, state_code, counties=None, columns=None):
    """``population_source`` + ``read_population`` for one run; returns (population, source_name)."""
    path, source_name = population_source(results_dir, state_code, counties)
    logger.info(f"Loading population {path}")
    return read_population(path, columns, state_code, counties), source_name
