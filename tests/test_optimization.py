"""Preserve original assignments and geometry rules while avoiding repeated work."""
from types import SimpleNamespace

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point, box

from src.assign_household import __assign_left_pop_hhold__, _left_household_choices
from src.tools import check_urban, classify_urban


@pytest.mark.parametrize('seed, expected, next_draws', [
    (42, ['h3', 'h3', 'h10', 'h10', 'h0', 'h9', 'h10', 'old'],
     [0.7860643052769538, 0.12811363267554587, 0.45038593789556713]),
    (7, ['h3', 'h6', 'h10', 'h2', 'h3', 'h6', 'h1', 'old'],
     [0.8212284183827663, 0.7970694287520462, 0.4679349528437208]),
])
def test_leftover_assignments_match_original(seed, expected, next_draws):
    # Expected assignments and subsequent draws were captured before optimization.
    households = pd.DataFrame({'hid': [f'h{i}' for i in range(11)], 'htype': range(11)})
    people = pd.DataFrame({'age': [0, 17, 18, 19, 70, 4, 18, 45],
                           'assigned': [0] * 7 + [1], 'hhold': ['old'] * 8, 'htype': [11] * 8})
    rng = np.random.default_rng(seed)
    choices = _left_household_choices(households)
    results = [__assign_left_pop_hhold__(p, households, rng, choices)
               for p in people.itertuples(index=False)]
    assert [r[0] for r in results] == expected
    assert [r[1] for r in results] == [int(h[1:]) if h != 'old' else 11 for h in expected]
    assert all(r[2] == 1 for r in results)
    np.testing.assert_array_equal(rng.random(3), next_draws)


def test_child_fallback_and_no_suitable_household(capsys):
    rng = np.random.default_rng(42)
    person = SimpleNamespace(age=4, assigned=0)
    households = pd.DataFrame({'hid': ['roommates'], 'htype': [10]})
    assert __assign_left_pop_hhold__(person, households, rng) == ('roommates', 10, 1)
    households = pd.DataFrame({'hid': ['alone'], 'htype': [4]})
    state = rng.bit_generator.state
    for age, message in [(4, 'kids'), (18, '18 adults'), (40, 'adults')]:
        person.age = age
        assert __assign_left_pop_hhold__(person, households, rng) is None
        assert capsys.readouterr().out == f'No suitable households available for {message}\n'
    assert rng.bit_generator.state == state


def test_global_numpy_fallback_is_preserved():
    households = pd.DataFrame({'hid': ['a', 'b'], 'htype': [1, 10]})
    person = SimpleNamespace(age=18, assigned=0)
    state = np.random.get_state()
    try:
        np.random.seed(42)
        expected = np.random.choice(['a', 'b'], p=[0.25, 0.75])
        following = np.random.random()
        np.random.seed(42)
        assert __assign_left_pop_hhold__(person, households)[0] == expected
        assert np.random.random() == following
    finally:
        np.random.set_state(state)


def test_urban_matches_scalar_for_shared_homes_and_boundaries():
    # Overlapping polygons, an interior hole, boundary points, and duplicate homes.
    polygon = box(0, 0, 4, 4).difference(box(1, 1, 2, 2))
    boundary = gpd.GeoDataFrame(geometry=[polygon, box(3, 3, 6, 6), None], crs='EPSG:4269')
    points = [Point(0, 0), Point(1.5, 1.5), Point(1, 1.5), Point(3.5, 3.5),
              Point(10, 10), Point(0, 0), Point(3.5, 3.5)]
    people = gpd.GeoDataFrame(geometry=points, index=['z', 'a', 'd', 'b', 'x', 'r', 's'],
                              crs=boundary.crs)
    expected = people.apply(lambda row: check_urban(row, boundary), axis=1)
    pd.testing.assert_series_equal(classify_urban(people, boundary), expected)


def test_urban_empty_inputs_and_missing_home():
    boundary = gpd.GeoDataFrame(geometry=[], crs='EPSG:4269')
    people = gpd.GeoDataFrame(geometry=[Point(0, 0)], crs=boundary.crs)
    assert classify_urban(people, boundary).tolist() == [False]
    assert classify_urban(people.iloc[:0], boundary).empty
    people.geometry = [None]
    with pytest.raises(AttributeError, match="'NoneType' object has no attribute 'intersects'"):
        classify_urban(people, boundary)
