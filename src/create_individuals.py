"""Expand Census age/sex counts into synthetic people."""
import pandas as pd


# Preserve the original male-then-female order without relying on input column positions.
AGE_SEX_COLUMNS = ([f'DP1_{n:04d}C' for n in range(26, 44)]
                   + [f'DP1_{n:04d}C' for n in range(50, 68)])


def create_individuals(tract, rng=None):
    """Generate ages, Census sex categories, and tract-based person IDs.

    Remainders go to the last age of each five-year group, including 85–89 for
    the open-ended 85+ group. With no generator, keep the original shuffle seed 123.
    """
    age_sex_groups = tract.loc[AGE_SEX_COLUMNS].astype(int)
    individual_dfs = []
    for code, count in enumerate(age_sex_groups):
        base_age = (code % 18) * 5
        gender = 'm' if code < 18 else 'f'
        ages = []
        for offset in range(4):
            ages.extend([offset + base_age] * (count // 5))
        ages.extend([base_age + 4] * (count - len(ages)))
        individual_dfs.append(pd.DataFrame({'code': code, 'age': ages, 'gender': [gender] * count}))

    people = pd.concat(individual_dfs).sample(
        frac=1, random_state=123 if rng is None else rng).reset_index(drop=True)
    people.index = tract.name + 'i' + people.index.to_series().astype(str)
    return people
