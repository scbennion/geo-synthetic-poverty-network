"""Preserve original assignments and geometry rules while avoiding repeated work."""
from types import SimpleNamespace
import random

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point, box

from pipeline.population.assign_household import __assign_left_pop_hhold__, _left_household_choices
from pipeline.population.create_space import check_urban
from pipeline.population.create_space import classify_urban
from pipeline.population.assign_household import (
    __htype_find_members__, __get_kids_or_friend__, _MemberPool,
    _write_household_members, _write_household_members_scalar,
)


@pytest.mark.parametrize('kind, expected', [
    (0, ['p34', 'p119']), (1, ['p34', 'p119', ['p101', 'p8']]),
    (2, ['p34', 'p119']), (3, ['p34', 'p119', ['p101', 'p8']]),
    (4, ['p58']), (5, ['p85']), (6, ['p32', ['p0']]),
    (7, ['p148']), (8, ['p175']), (9, ['p122', ['p0']]),
    (10, ['p46', ['p32']]),
])
def test_member_selection_matches_captured_assignments(kind, expected):
    people = pd.DataFrame({'age': list(range(90)) * 2, 'gender': ['m'] * 90 + ['f'] * 90,
                           'assigned': 0}, index=[f'p{i}' for i in range(180)])
    state = random.getstate()
    try:
        random.seed(42)
        actual = __htype_find_members__(kind, people, np.random.default_rng(42))
    finally:
        random.setstate(state)
    assert actual == expected
    assigned = [person for group in expected for person in (group if isinstance(group, list) else [group])]
    assert set(people.index[people.assigned == 1]) == set(assigned)


def test_pool_preserves_order_and_excludes_assigned_people():
    people = pd.DataFrame({'age': [64.5, 65, 18, 30], 'gender': ['m', 'm', 'f', 'm'],
                           'assigned': [0, 0, 0, 1]}, index=['z', 'b', 'a', 'x'])
    pool = _MemberPool(people)
    assert pool.available(18, 65, 'm', upper_exclusive=True).tolist() == ['z']
    assert pool.available(18).tolist() == ['z', 'b', 'a']
    pool.assign(['z', 'a'])
    assert pool.available(18).tolist() == ['b']
    pool.flush()
    assert people.assigned.tolist() == [1, 0, 1, 1]


def test_integer_zero_index_retains_legacy_selection_behavior():
    people = pd.DataFrame({'age': [30], 'gender': ['m'], 'assigned': [0]})
    assert __htype_find_members__(4, people) == []
    assert people.assigned.tolist() == [0]


def test_unavailable_partner_preserves_partial_assignment():
    people = pd.DataFrame({'age': [24], 'gender': ['m'], 'assigned': [0]}, index=['head'])
    with pytest.raises(IndexError):
        __htype_find_members__(0, people)
    assert people.loc['head', 'assigned'] == 1


def test_children_fallback_preserves_empty_and_insufficient_adults():
    people = pd.DataFrame({'age': [40], 'gender': ['m'], 'assigned': [0]}, index=['adult'])
    with pytest.raises(ValueError):
        __get_kids_or_friend__(10, 0, people, 2)
    people['assigned'] = 1
    assert __get_kids_or_friend__(10, 0, people, 1) is None


@pytest.mark.parametrize('members', [
    [['a', ['b', 'c']], ['a']],  # last household wins for a repeated person
    [[['a', 'b']], [['c']]],    # nested group-quarters lists
    [['a', None], ['b']],      # retain the legacy missing-member behavior
    [[], []],
])
def test_grouped_writeback_matches_scalar(members):
    households = pd.DataFrame({'hid': ['h0', 'h1'], 'htype': [1, 11], 'member': members})
    people = pd.DataFrame({'age': [10, 20, 30], 'assigned': [1, 1, 1]}, index=['a', 'b', 'c'])
    expected = people.copy()
    _write_household_members_scalar(households, expected)
    _write_household_members(households, people)
    pd.testing.assert_frame_equal(people, expected)


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
