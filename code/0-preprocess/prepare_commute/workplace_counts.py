"""Estimate workplace counts from tract jobs and county establishments."""
from loguru import logger


def tract_geoid(value):
    """11-digit tract GEOID string, restoring leading zeros lost to int parsing."""
    s = str(value).strip()
    if s.endswith('.0'):
        s = s[:-2]
    return s.zfill(11)


def tract_and_county_jobs(od):
    """
    Jobs located in each work tract (J_t) and in each county (J_c) from an OD table
    with 'work' tract and 'S000' columns. Returns two Series indexed by 11-digit
    tract GEOID and 5-digit county FIPS.
    """
    work = od['work'].map(tract_geoid)
    tract_jobs = od['S000'].groupby(work).sum()
    county_jobs = tract_jobs.groupby(tract_jobs.index.str[:5]).sum()
    return tract_jobs, county_jobs


def get_number_of_wp(data, od, campany_df, state_code, error_tract, jobs=None):
    """
    Number of workplaces for a tract: floor(B_c * J_t / J_c), where B_c is the CBP
    establishment count (ESTAB) of the tract's own county, J_t the jobs located in the
    tract and J_c the jobs located in that county (both from the OD 'work' side).

    The county is the first 5 digits of the 11-digit GEOID for every state;
    `state_code` is kept for call compatibility. Pass `jobs` (the result of
    `tract_and_county_jobs(od)`) to avoid regrouping `od` for every tract.
    Tracts with no OD jobs, no CBP county row, or zero county jobs return 0 and
    are appended to `error_tract`, as before.
    """
    tract_number = str(data.GEOID)
    try:
        tract_jobs, county_jobs = jobs if jobs is not None else tract_and_county_jobs(od)
        geoid = tract_geoid(tract_number)
        county_number = geoid[:5]

        tract_jobs_number = int(tract_jobs.loc[geoid])
        county_job_number = int(county_jobs.loc[county_number])

        estab = campany_df.loc[campany_df['county'].map(lambda c: str(c).zfill(5)) == county_number, 'ESTAB']
        county_company_number = int(estab.values[0])
        return int(county_company_number * (tract_jobs_number / county_job_number))

    except Exception:
        logger.info(f"{tract_number} has issue")
        error_tract.append(tract_number)
        return 0


def add_workplace_counts(state_census, od_df, cbp, state_code):
    """Adds WP_CNT using get_number_of_wp; returns (gdf, error_tracts). Same as add_tract_workplaces.py."""
    state_census = state_census.copy()
    error_tract = []
    state_census['WP_CNT'] = state_census.apply(get_number_of_wp, args=(od_df, cbp, state_code, error_tract),
                                                axis=1)
    return state_census, error_tract
