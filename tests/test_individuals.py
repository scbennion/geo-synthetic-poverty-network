"""Expected results captured before the readability refactor."""
import numpy as np
import pandas as pd
import pytest

from pipeline.population_synthesis.create_individuals import create_individuals


@pytest.fixture
def tract():
    columns = [f'lead{i}' for i in range(13)]
    columns += [f'DP1_{n:04d}C' for n in range(26, 44)]
    columns += ['DP1_0049C'] + [f'DP1_{n:04d}C' for n in range(50, 68)]
    row = pd.Series(0, index=columns, name='49035000100')
    row['DP1_0026C'], row['DP1_0043C'], row['DP1_0051C'] = 7, 1, 3
    return row


@pytest.mark.parametrize('seed, ages, next_random', [
    (None, [0, 4, 4, 89, 9, 9, 3, 1, 4, 9, 2], None),
    (7, [1, 2, 4, 4, 89, 4, 9, 0, 9, 9, 3], 0.3030324268193135),
    (42, [1, 3, 89, 0, 2, 4, 9, 9, 4, 9, 4], 0.37079802423258124),
])
def test_captured_people_and_random_stream(tract, seed, ages, next_random):
    rng = None if seed is None else np.random.default_rng(seed)
    people = create_individuals(tract, rng)
    expected = pd.DataFrame({
        'code': [17 if age == 89 else 19 if age == 9 else 0 for age in ages],
        'age': [float(age) for age in ages],
        'gender': ['f' if age == 9 else 'm' for age in ages],
    }, index=[f'{tract.name}i{i}' for i in range(len(ages))])
    expected['gender'] = expected['gender'].astype(object)
    pd.testing.assert_frame_equal(people, expected)
    if rng is not None:
        assert rng.random() == next_random


def test_zero_counts_keep_empty_population_schema(tract):
    people = create_individuals(tract * 0, np.random.default_rng(42))
    assert people.empty
    assert list(people.columns) == ['code', 'age', 'gender']


def test_named_fields_ignore_column_order_and_unrelated_values(tract):
    expected = create_individuals(tract, np.random.default_rng(42))
    reordered = tract.iloc[::-1].copy()
    reordered['unrelated_count'] = 999
    actual = create_individuals(reordered, np.random.default_rng(42))
    pd.testing.assert_frame_equal(actual, expected)


def test_missing_age_field_is_reported(tract):
    with pytest.raises(KeyError, match='DP1_0067C'):
        create_individuals(tract.drop('DP1_0067C'))
