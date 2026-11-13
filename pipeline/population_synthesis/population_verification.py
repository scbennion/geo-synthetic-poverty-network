"""Per-tract checks recorded during population synthesis."""
import pandas as pd


def verify_population(tract, people):
    """Return differences between tract targets and generated population counts."""
    ver_df = {}
    # 3.1 population uder each age group
    ver_df['pop_diff'] = tract.DP1_0001C - len(people)
    # age 0 to 19
    # age 20 to 64
    ver_df['male_adults_diff'] = tract.DP1_0025C - len(people[people.gender == 'm'])
    ver_df['female_adults_diff'] = tract.DP1_0049C - len(people[people.gender == 'f'])

    ver_df['m_diff_0_4'] = tract.DP1_0026C - len(people[(people.gender == 'm') & (people.age >= 0) & (people.age <= 4)])
    ver_df['m_diff_5_9'] = tract.DP1_0027C - len(people[(people.gender == 'm') & (people.age >= 5) & (people.age <= 9)])
    ver_df['m_diff_10_14'] = tract.DP1_0028C - len(
        people[(people.gender == 'm') & (people.age >= 10) & (people.age <= 14)])
    ver_df['m_diff_15_19'] = tract.DP1_0029C - len(
        people[(people.gender == 'm') & (people.age >= 15) & (people.age <= 19)])
    ver_df['m_diff_20_24'] = tract.DP1_0030C - len(
        people[(people.gender == 'm') & (people.age >= 20) & (people.age <= 24)])
    ver_df['m_diff_25_29'] = tract.DP1_0031C - len(
        people[(people.gender == 'm') & (people.age >= 25) & (people.age <= 29)])
    ver_df['m_diff_30_34'] = tract.DP1_0032C - len(
        people[(people.gender == 'm') & (people.age >= 30) & (people.age <= 34)])
    ver_df['m_diff_35_39'] = tract.DP1_0033C - len(
        people[(people.gender == 'm') & (people.age >= 35) & (people.age <= 39)])
    ver_df['m_diff_40_44'] = tract.DP1_0034C - len(
        people[(people.gender == 'm') & (people.age >= 40) & (people.age <= 44)])
    ver_df['m_diff_45_49'] = tract.DP1_0035C - len(
        people[(people.gender == 'm') & (people.age >= 45) & (people.age <= 49)])
    ver_df['m_diff_50_54'] = tract.DP1_0036C - len(
        people[(people.gender == 'm') & (people.age >= 50) & (people.age <= 54)])
    ver_df['m_diff_55_59'] = tract.DP1_0037C - len(
        people[(people.gender == 'm') & (people.age >= 55) & (people.age <= 59)])
    ver_df['m_diff_60_64'] = tract.DP1_0038C - len(
        people[(people.gender == 'm') & (people.age >= 60) & (people.age <= 64)])
    ver_df['m_diff_65_69'] = tract.DP1_0039C - len(
        people[(people.gender == 'm') & (people.age >= 65) & (people.age <= 69)])
    ver_df['m_diff_70_74'] = tract.DP1_0040C - len(
        people[(people.gender == 'm') & (people.age >= 70) & (people.age <= 74)])
    ver_df['m_diff_75_79'] = tract.DP1_0041C - len(
        people[(people.gender == 'm') & (people.age >= 75) & (people.age <= 79)])
    ver_df['m_diff_80_84'] = tract.DP1_0042C - len(
        people[(people.gender == 'm') & (people.age >= 80) & (people.age <= 84)])
    ver_df['m_diff_85'] = tract.DP1_0043C - len(people[(people.gender == 'm') & (people.age >= 85)])

    ver_df['f_diff_0_4'] = tract.DP1_0050C - len(people[(people.gender == 'f') & (people.age >= 0) & (people.age <= 4)])
    ver_df['f_diff_5_9'] = tract.DP1_0051C - len(people[(people.gender == 'f') & (people.age >= 5) & (people.age <= 9)])
    ver_df['f_diff_10_14'] = tract.DP1_0052C - len(
        people[(people.gender == 'f') & (people.age >= 10) & (people.age <= 14)])
    ver_df['f_diff_15_19'] = tract.DP1_0053C - len(
        people[(people.gender == 'f') & (people.age >= 15) & (people.age <= 19)])
    ver_df['f_diff_20_24'] = tract.DP1_0054C - len(
        people[(people.gender == 'f') & (people.age >= 20) & (people.age <= 24)])
    ver_df['f_diff_25_29'] = tract.DP1_0055C - len(
        people[(people.gender == 'f') & (people.age >= 25) & (people.age <= 29)])
    ver_df['f_diff_30_34'] = tract.DP1_0056C - len(
        people[(people.gender == 'f') & (people.age >= 30) & (people.age <= 34)])
    ver_df['f_diff_35_39'] = tract.DP1_0057C - len(
        people[(people.gender == 'f') & (people.age >= 35) & (people.age <= 39)])
    ver_df['f_diff_40_44'] = tract.DP1_0058C - len(
        people[(people.gender == 'f') & (people.age >= 40) & (people.age <= 44)])
    ver_df['f_diff_45_49'] = tract.DP1_0059C - len(
        people[(people.gender == 'f') & (people.age >= 45) & (people.age <= 49)])
    ver_df['f_diff_50_54'] = tract.DP1_0060C - len(
        people[(people.gender == 'f') & (people.age >= 50) & (people.age <= 54)])
    ver_df['f_diff_55_59'] = tract.DP1_0061C - len(
        people[(people.gender == 'f') & (people.age >= 55) & (people.age <= 59)])
    ver_df['f_diff_60_64'] = tract.DP1_0062C - len(
        people[(people.gender == 'f') & (people.age >= 60) & (people.age <= 64)])
    ver_df['f_diff_65_69'] = tract.DP1_0063C - len(
        people[(people.gender == 'f') & (people.age >= 65) & (people.age <= 69)])
    ver_df['f_diff_70_74'] = tract.DP1_0064C - len(
        people[(people.gender == 'f') & (people.age >= 70) & (people.age <= 74)])
    ver_df['f_diff_75_79'] = tract.DP1_0065C - len(
        people[(people.gender == 'f') & (people.age >= 75) & (people.age <= 79)])
    ver_df['f_diff_80_84'] = tract.DP1_0066C - len(
        people[(people.gender == 'f') & (people.age >= 80) & (people.age <= 84)])
    ver_df['f_diff_85'] = tract.DP1_0067C - len(people[(people.gender == 'f') & (people.age >= 85)])

    hhold_df = people.drop_duplicates(subset=['hhold'], keep='first')

    if tract.DP1_0132C == 0:
        ver_df['htye0'] = 0
        # 1 marrie with kids: DP1_0134C
        ver_df['htye1'] = 0
        # 2 cocahbiting          : DP1_0135C - DP1_0136C
        ver_df['htye2'] = 0
        # 3 cocahbiting with Kids: DP1_0136C
        ver_df['htye3'] = 0

        # 4 male live alone        :DP1_0138C - DP1_0139C
        ver_df['htye4'] = 0
        # 5 male senior live alone :DP1_0139C
        ver_df['htye5'] = 0

        # 6 male with kids         :DP1_0140C
        ver_df['htye6'] = 0

        # 7  female live alone        :DP1_0142C - DP1_0143C
        ver_df['htye7'] = 0

        # 8  female senior live alone :DP1_0143C
        ver_df['htye8'] = 0

        # 9  female with kids         :DP1_0144C
        ver_df['htye9'] = 0

        # 10 non-family group         : (DP1_0137C - DP1_0138C - DP1_0140C) + (DP1_0141C - DP1_0142C - DP1_0144C)
        ver_df['htye10'] = 0

        # only group quarter
        ver_df['htye11'] = len(hhold_df[(hhold_df.htype == 11)])

    else:
        ver_df['htye0'] = (tract.DP1_0133C - tract.DP1_0134C) - len(hhold_df[(hhold_df.htype == 0)])
        # 1 marrie with kids: DP1_0134C
        ver_df['htye1'] = tract.DP1_0134C - len(hhold_df[(hhold_df.htype == 1)])
        # 2 cocahbiting          : DP1_0135C - DP1_0136C
        ver_df['htye2'] = (tract.DP1_0135C - tract.DP1_0136C) - len(hhold_df[(hhold_df.htype == 2)])
        # 3 cocahbiting with Kids: DP1_0136C
        ver_df['htye3'] = tract.DP1_0136C - len(hhold_df[(hhold_df.htype == 3)])

        # 4 male live alone        :DP1_0138C - DP1_0139C
        ver_df['htye4'] = (tract.DP1_0138C - tract.DP1_0139C) - len(hhold_df[(hhold_df.htype == 4)])
        # 5 male senior live alone :DP1_0139C
        ver_df['htye5'] = tract.DP1_0139C - len(hhold_df[(hhold_df.htype == 5)])

        # 6 male with kids         :DP1_0140C
        ver_df['htye6'] = tract.DP1_0140C - len(hhold_df[(hhold_df.htype == 6)])

        # 7  female live alone        :DP1_0142C - DP1_0143C
        ver_df['htye7'] = (tract.DP1_0142C - tract.DP1_0143C) - len(hhold_df[(hhold_df.htype == 7)])

        # 8  female senior live alone :DP1_0143C
        ver_df['htye8'] = tract.DP1_0143C - len(hhold_df[(hhold_df.htype == 8)])

        # 9  female with kids         :DP1_0144C
        ver_df['htye9'] = tract.DP1_0144C - len(hhold_df[(hhold_df.htype == 9)])

        # 10 non-family group         : (DP1_0137C - DP1_0138C - DP1_0140C) + (DP1_0141C - DP1_0142C - DP1_0144C)
        ver_df['htye10'] = ((tract.DP1_0137C - tract.DP1_0138C - tract.DP1_0140C) + (
                    tract.DP1_0141C - tract.DP1_0142C - tract.DP1_0144C)) - len(hhold_df[(hhold_df.htype == 10)])

        ver_df['htye11'] = len(hhold_df[(hhold_df.htype == 11)])

    # 3.2 AVG hhold size
    return pd.Series(ver_df, name=tract.name)
