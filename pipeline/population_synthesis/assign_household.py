import random
import pandas as pd
import numpy as np

def __assign_household_order__(tract, people, rng=None):
    # rng: numpy Generator for the numpy draws; Python `random` draws use the global seed


    # 1.3 use hholdid and hhhold htype to find individuals
    people['assigned'] = 0

    if tract.DP1_0132C == 0:  # if there is nor houshold record in the census tract, create groupquarter
        print("---only group quarter---")
        gq_df = __get_group_quarter__(tract, people)
        # left people
        people['hhold'] = gq_df['hid'][0]
        people['htype'] = 11
        people['assigned'] = 1
    else:
        # 1 get household and its member
        # 1.1 extract amount of each household type
        hhold_df_type = __get_hhold_type__(tract)

        # add a col to indicate household type
        hhold_df_type['htype'] = hhold_df_type.index  # np.repeat(hhold_df_type.index, hhold_df_type)

        # 1.2 create hhold df with cols hid, htype using hhold_df_type
        hhold_df = __creat_hhold_id__(tract, hhold_df_type)

        # 1.3 find members using hhold type
        pool = _MemberPool(people)
        try:
            hhold_df['member'] = [__htype_find_members__(kind, pool, rng) for kind in hhold_df.htype]
        finally:
            pool.flush()

        # 2, group unassigned population based on group quarters
        # 2.1 find gp population
        gp_df = __get_group_quarter__(tract, people)
        # 2.1 combine
        hhold_df = pd.concat([hhold_df, gp_df])

        # 3 , add two cols to people df: 1 is hhold, the other is hhold type
        _write_household_members(hhold_df, people)

        # 4 assign left population randomly to household other than alone household
        choices = _left_household_choices(hhold_df)
        results = [__assign_left_pop_hhold__(row, hhold_df, rng, choices)
                   for row in people[['age', 'assigned', 'hhold', 'htype']].itertuples(index=False)]
        people[['hhold', 'htype', 'assigned']] = pd.DataFrame(
            [result if result is not None else (np.nan, np.nan, np.nan) for result in results],
            index=people.index, columns=['hhold', 'htype', 'assigned'])


def __get_hhold_type__(tract):
    """Return tract targets for the eleven regular household categories."""

    hhold_type_amount = pd.Series(np.zeros(11), dtype=int)

    # 0 married         : DP1_0133C - DP1_0134C
    hhold_type_amount[0] = tract.DP1_0133C - tract.DP1_0134C
    # 1 marrie with kids: DP1_0134C
    hhold_type_amount[1] = tract.DP1_0134C

    # 2 cocahbiting          : DP1_0135C - DP1_0136C
    hhold_type_amount[2] = tract.DP1_0135C - tract.DP1_0136C
    # 3 cocahbiting with Kids: DP1_0136C
    hhold_type_amount[3] = tract.DP1_0136C

    # 4 male live alone        :DP1_0138C - DP1_0139C
    hhold_type_amount[4] = tract.DP1_0138C - tract.DP1_0139C
    # 5 male senior live alone :DP1_0139C
    hhold_type_amount[5] = tract.DP1_0139C

    # 6 male with kids         :DP1_0140C
    hhold_type_amount[6] = tract.DP1_0140C

    # 7  female live alone        :DP1_0142C - DP1_0143C
    hhold_type_amount[7] = tract.DP1_0142C - tract.DP1_0143C

    # 8  female senior live alone :DP1_0143C
    hhold_type_amount[8] = tract.DP1_0143C

    # 9  female with kids         :DP1_0144C
    hhold_type_amount[9] = tract.DP1_0144C

    # 10 non-family group         : (DP1_0137C - DP1_0138C - DP1_0140C) + (DP1_0141C - DP1_0142C - DP1_0144C)
    hhold_type_amount[10] = (tract.DP1_0137C - tract.DP1_0138C - tract.DP1_0140C) + (
                tract.DP1_0141C - tract.DP1_0142C - tract.DP1_0144C)

    hhold_type_amount = pd.DataFrame({'amount': hhold_type_amount})


    return hhold_type_amount


def __creat_hhold_id__(tract, df_type):
    """
        1.2 create hhold based on the hhold type;
        Create household IDs and types based on the provided census tract data and household type DataFrame.

    Parameters:
        -  tract: Census tract data containing information about the tract.
        - df_type: DataFrame containing household type information.

    Returns:
        - DataFrame: DataFrame with columns 'hid' for household IDs and 'htype' for household types.
    """
    hid_list = []
    type_list = []

    # Generate household IDs and types
    current_hid = 0

    for index, row in df_type.iterrows():
        htype = row['htype']
        amount = row['amount']
        for _ in range(amount):
            hid_list.append(tract.name + 'h' + str(current_hid))
            type_list.append(htype)
            current_hid += 1

    # Create DataFrame from the lists
    df = pd.DataFrame({'hid': hid_list, 'htype': type_list})

    custom_order = [4, 5, 7, 8, 0, 1, 2, 3, 9, 10, 6]
    df['htype'] = pd.Categorical(df['htype'], categories=custom_order, ordered=True)
    df_type = df.sort_values(by='htype').reset_index(drop=True)
    df_type['htype'] = df_type['htype'].astype(int)


    return df_type


class _MemberPool:
    """Array views for sequential selection, retaining the population's index order."""

    def __init__(self, people):
        self.people = people
        self.index = people.index
        self.ages = people['age'].to_numpy()
        self.gender = people['gender'].to_numpy()
        self.assigned = people['assigned'].to_numpy(copy=True)

    def available(self, lower=0, upper=np.inf, gender=None, upper_exclusive=False):
        below_upper = self.ages < upper if upper_exclusive else self.ages <= upper
        mask = (self.assigned == 0) & (self.ages >= lower) & below_upper
        if gender is not None:
            mask &= self.gender == gender
        return self.index[mask]

    def assign(self, ids):
        self.assigned[self.index.get_indexer(np.atleast_1d(ids))] = 1

    def age(self, person):
        return self.ages[self.index.get_loc(person)]

    def minimum_age(self, ids):
        ages = self.ages[self.index.get_indexer(np.atleast_1d(ids))]
        ages = ages[~pd.isna(ages)]
        return ages.min() if len(ages) else np.nan

    def flush(self):
        self.people['assigned'] = self.assigned


def __htype_find_members__(type, people, rng=None):
    """Select members with the original candidate order and scalar random draws."""
    pool = people if isinstance(people, _MemberPool) else _MemberPool(people)
    try:
        return _select_members(type, pool, np.random if rng is None else rng)
    finally:
        if pool is not people:
            pool.flush()


def _select_members(kind, pool, rng):
    members = []
    if kind in (4, 5, 7, 8):
        gender = 'm' if kind in (4, 5) else 'f'
        lower, upper = (18, 65) if kind in (4, 7) else (65, np.inf)
        candidates = pool.available(lower, upper, gender, upper_exclusive=kind in (4, 7))
        # Keep Index.any(), including its legacy behavior for an integer index of 0.
        if candidates.any():
            person = random.choice(candidates)
            pool.assign(person)
            members.append(person)

    if kind in (0, 1, 2, 3):
        candidates = pool.available(20, gender='m')
        if len(candidates):
            head = random.choice(candidates)
            pool.assign(head)
            members.append(head)
            age = pool.age(head)
            if 20 <= age <= 25:
                candidates = pool.available(18, age + 15, 'f')
            else:
                candidates = pool.available(age - 5, age + 15, 'f')
                if not len(candidates):
                    candidates = pool.available(20, np.nanmax(pool.ages), 'f')
            partner = random.choice(candidates)
            pool.assign(partner)
            members.append(partner)

    if kind in (1, 3):
        upper, lower = __get_kids_max_min_age__(members, pool)
        number = max(1, abs(int(rng.normal(2))))
        members.append(__get_kids_or_friend__(upper, lower, pool, number))

    if kind in (6, 9):
        candidates = pool.available(18, gender='m' if kind == 6 else 'f')
        if candidates.any():
            head = random.choice(candidates)
            pool.assign(head)
            members.append(head)
            number = max(1, abs(int(rng.normal(1.6))))
            upper, lower = __get_kids_max_min_age__(head, pool)
            members.append(__get_kids_or_friend__(upper, lower, pool, number))

    if kind == 10:
        candidates = pool.available(18)
        if candidates.any():
            head = random.choice(candidates)
            pool.assign(head)
            members.append(head)
            number = max(1, abs(int(rng.normal(1.5))))
            age = pool.age(head)
            lower = 18 if 18 <= age <= 22 else age - 15
            members.append(__get_kids_or_friend__(age + 15, lower, pool, number))
    return members


def __get_kids_max_min_age__(indi_list, people):
    age = (people.minimum_age(indi_list) if isinstance(people, _MemberPool)
           else people.loc[indi_list, 'age'].min())
    upper = age - 18
    return (18 if upper > 18 else upper), 0


def __get_kids_or_friend__(age_max, age_min, people, number):
    pool = people if isinstance(people, _MemberPool) else _MemberPool(people)
    try:
        candidates = list(pool.available(age_min, age_max))
        if len(candidates) < number:
            candidates = list(pool.available(18))
            if not candidates:
                return None
        selected = random.sample(candidates, number)
        pool.assign(selected)
        return selected
    finally:
        if pool is not people:
            pool.flush()


def _write_household_members(households, people):
    """Collect membership in household order, then write each column once."""
    assignments = {}
    for household in households.itertuples(index=False):
        for member in household.member:
            ids = member if isinstance(member, list) else [member]
            for person in ids:
                if person not in people.index:
                    # Preserve legacy handling of missing/invalid member IDs.
                    return _write_household_members_scalar(households, people)
                assignments[person] = (household.hid, household.htype)
    if not assignments:
        return
    records = pd.DataFrame.from_dict(assignments, orient='index', columns=['hhold', 'htype'])
    if 'hhold' not in people:
        people['hhold'] = records['hhold'].reindex(people.index)
    if 'htype' not in people:
        people['htype'] = np.nan
    people.loc[records.index, 'hhold'] = records['hhold']
    people.loc[records.index, 'htype'] = records['htype']


def _write_household_members_scalar(households, people):
    for household in households.itertuples(index=False):
        for member in household.member:
            people.loc[member, 'hhold'] = household.hid
            people.loc[member, 'htype'] = household.htype


def __get_group_quarter__(tract, people):
    '''
    2 use group quarter info to assign population to group quarter
    2.1 get the population under  each group quarter type then find individuals
    '''
    # tract.DP1_0127C
    members = []
    # Institutionalized population:!!Male
    #
    if tract.DP1_0127C == 0:
        pass
    else:
        members.append(__get_group_quarter_ids__('male', people, 64, 18, tract.DP1_0127C))
    # Institutionalized population:!!Female

    #
    if tract.DP1_0128C == 0:
        pass
    else:
        members.append(__get_group_quarter_ids__('female', people, 64, 18, tract.DP1_0128C))

    if tract.DP1_0130C == 0:
        pass
    else:
        members.append(__get_group_quarter_ids__('male', people, 100, 18, tract.DP1_0130C))

    if tract.DP1_0131C == 0:
        pass
    else:
        members.append(__get_group_quarter_ids__('female', people, 100, 18, tract.DP1_0131C))

    gp_data = {
        'hid': tract.name + 'h' + str(tract.DP1_0132C),
        'htype': 11,
        'member': members
    }
    return pd.DataFrame(gp_data)


def __get_group_quarter_ids__(x, people, upper_age, lower_age, number):
    '''
    2.2 use census to get group quarter member ids
    '''
    member_list = []
    if x == 'male':
        selected_index_list = people[(people['age'] <= upper_age) &
                                          (people['age'] >= lower_age) &
                                          (people['gender'] == 'm') &
                                          (people['assigned'] == 0)].index

        if len(selected_index_list) >= number:
            id_index = random.sample(list(selected_index_list), number)
            people.loc[id_index, 'assigned'] = 1
            member_list.append(id_index)
        else:
            # Handle the case where there are not enough eligible indices
            selected_index_list = people[(people['age'] >= 0) & (people['gender'] == 'm') & (people['assigned'] == 0)].index
            if len(selected_index_list) >= number:
                id_index = random.sample(list(selected_index_list), number)
                people.loc[id_index, 'assigned'] = 1
                member_list.append(id_index)
            else:
                pass

    if x == 'female':
        selected_index_list = people[(people['age'] <= upper_age) &
                                          (people['age'] >= lower_age) &
                                          (people['gender'] == 'f') &
                                          (people['assigned'] == 0)].index

        if len(selected_index_list) >= number:
            id_index = random.sample(list(selected_index_list), number)
            people.loc[id_index, 'assigned'] = 1
            member_list.append(id_index)
        else:
            # Handle the case where there are not enough eligible indices
            selected_index_list = people[(people['age'] >= 0) & (people['gender'] == 'f') & (people['assigned'] == 0)].index
            if len(selected_index_list) >= number:
                id_index = random.sample(list(selected_index_list), number)
                people.loc[id_index, 'assigned'] = 1
                member_list.append(id_index)
            else:
                pass
    return member_list


def _left_household_choices(hhold_df):
    """Household candidates do not change while placing leftover people."""
    choices = {}
    for group, types, weights in (
        ('kid', [1, 3, 6, 9], {1: 0.45, 3: 0.45, 6: 0.1, 9: 0.1}),
        ('eighteen', [1, 3, 10], {1: 0.2, 3: 0.2, 10: 0.6}),
        ('adult', [0, 1, 2, 3, 10], {0: 0.1, 1: 0.1, 2: 0.1, 3: 0.1, 10: 0.6}),
    ):
        candidates = hhold_df[hhold_df['htype'].isin(types)]
        ids = list(candidates.hid)
        probabilities = np.array([weights[t] for t in candidates.htype])
        if ids:
            probabilities = probabilities / np.sum(probabilities)
        choices[group] = (ids, probabilities)
    choices['kid_fallback'] = (list(hhold_df[hhold_df['htype'] == 10].hid), None)
    # Match the original first-row lookup even when a household ID is repeated.
    choices['types'] = hhold_df.drop_duplicates('hid').set_index('hid')['htype'].to_dict()
    return choices


def __assign_left_pop_hhold__(individual, hhold_df, rng=None, choices=None):
    """Place one leftover person using optional choices prepared for this tract."""
    rng = np.random if rng is None else rng  # numpy Generator; None = global np.random
    if individual.assigned != 0:
        return individual.hhold, individual.htype, individual.assigned

    choices = _left_household_choices(hhold_df) if choices is None else choices
    if individual.age < 18:
        group, message = 'kid', 'kids'
    elif individual.age == 18:
        group, message = 'eighteen', '18 adults'
    elif individual.age > 18:
        group, message = 'adult', 'adults'
    else:
        return None

    ids, probabilities = choices[group]
    if not ids and group == 'kid':
        ids, probabilities = choices['kid_fallback']
    if not ids:
        print(f'No suitable households available for {message}')
        return None

    # Keep one scalar draw per person, in the original candidate order.
    if probabilities is None:
        household_id = rng.choice(ids)
    else:
        household_id = rng.choice(ids, p=probabilities)
    return household_id, choices['types'][household_id], 1
