from src.tools import new_distance
import pandas as pd
import geopandas as gpd
from loguru import logger
import random

# CRS the tract polygons and site points arrive in (NAD83 longitude/latitude).
GEOGRAPHIC_CRS = 'EPSG:4269'
# Metric CRS used for the tract search buffers. Utah-specific: NAD83 / UTM zone 12N.
# Other states need their own UTM/State Plane zone.
PROJECTED_CRS = 'EPSG:26912'
# Search buffers around the home tract polygon, in metres. These are the north-south
# equivalents of the original 0.1 and 0.9 degree buffers (see README "Education assignment").
NEAR_BUFFER_M = 11_000
FAR_BUFFER_M = 100_000


class EducationSites:
    '''
    School or daycare sites for one run, with a running enrollment counter keyed by eduID.

    Build one per site table per state run and pass the same object for every tract so the
    counter persists across tracts. The counter starts from the supplied ``count`` column.
    '''

    def __init__(self, sites, projected_crs=PROJECTED_CRS, source_crs=GEOGRAPHIC_CRS):
        sites = sites.set_index('eduID')
        if not sites.index.is_unique:
            raise ValueError('eduID values must be unique')
        if sites.crs is None:
            sites = sites.set_crs(source_crs)
        self.sites = sites
        self.projected_crs = projected_crs
        self.source_crs = source_crs
        self.projected_geometry = sites.geometry.to_crs(projected_crs)
        self.enrollment = sites['ENROLLMENT'].to_dict()
        self.count = sites['count'].fillna(0).to_dict()
        self.fallbacks = []  # (tract, age, eduID) for every over-capacity assignment

    def has_room(self, edu_id):
        return self.count[edu_id] < self.enrollment[edu_id]

    def add(self, edu_id):
        self.count[edu_id] += 1

    def snapshot(self):
        return dict(self.count), len(self.fallbacks)

    def restore(self, snap):
        '''Undo assignments made since ``snapshot()`` (used when a tract fails).'''
        count, n_fallbacks = snap
        self.count = dict(count)
        del self.fallbacks[n_fallbacks:]

    def counts(self):
        '''Current enrollment counter as a Series indexed by eduID.'''
        return pd.Series(self.count, name='count')


def _as_sites(edu, source_crs):
    if isinstance(edu, EducationSites):
        return edu
    # A plain GeoDataFrame gets a fresh counter that only lasts for this call.
    return EducationSites(edu, source_crs=source_crs)


def tract_buffers(geometry, tract_crs=GEOGRAPHIC_CRS, projected_crs=PROJECTED_CRS):
    '''(near, far) search buffers around a tract polygon, built in metres in ``projected_crs``.'''
    proj = gpd.GeoSeries([geometry], crs=tract_crs).to_crs(projected_crs).iloc[0]
    return proj.buffer(NEAR_BUFFER_M), proj.buffer(FAR_BUFFER_M)


def __assign_education_site__(tract, people, school, daycare, tract_crs=GEOGRAPHIC_CRS):
    '''
    All kids go to school and daycare
    :param tract: row of census tract (geometry in ``tract_crs``)
    :param people: people with home ``geometry`` and ``age``
    :param school: EducationSites (or school GeoDataFrame; then capacity is per call only)
    :param daycare: EducationSites (or daycare GeoDataFrame; then capacity is per call only)
    :param tract_crs: CRS of ``tract.geometry``
    :return:
    '''
    school = _as_sites(school, tract_crs)
    daycare = _as_sites(daycare, tract_crs)

    buffers = tract_buffers(tract.geometry, tract_crs, school.projected_crs)

    # Assign School
    school_kids_index = people[(people['age'] >= 5) & (people['age'] <= 17)].index
    for idx in school_kids_index:
        people.at[idx, "wp"] = __assign_eduID__(idx, tract, people, school, buffers)

    # Assign Daycare
    daycare_kids_index = people[(people['age'] <= 4)].index
    for idx in daycare_kids_index:
        people.at[idx, "wp"] = __assign_eduID__(idx, tract, people, daycare, buffers)  # .at is used to assign single value


def _sites_in(edu, buff, candidates):
    geom = edu.projected_geometry.loc[candidates.index]
    return candidates[geom.intersects(buff).to_numpy()]


def __assign_eduID__(data, tract, people, edu, buffers):
    '''

    :param data: kids info
    :param tract: row of census tract
    :param people: people generated in previous steps with geo-location info, this is used to get the kids info
    :param edu: EducationSites for daycare or school
    :param buffers: (near, far) tract buffers in the projected CRS
    :return: daycare or school id
    '''
    edu_df = edu.sites
    geo_loc = people.loc[data, 'geometry']
    kid_x = geo_loc.y
    kid_y = geo_loc.x
    age = people.loc[data, 'age']

    if age <= 4:  # daycare: no age filter
        edu_in_age = edu_df
    else:  # school
        edu_in_age = edu_df[(edu_df['s_age'] <= age) & (edu_df['e_age'] >= age)]

    # Search the near buffer; widen to the far buffer only if it has no candidates at all.
    edu_site_in_buffer = _sites_in(edu, buffers[0], edu_in_age)
    if len(edu_site_in_buffer) == 0:
        edu_site_in_buffer = _sites_in(edu, buffers[1], edu_in_age)

    return __find_edu_ID__(kid_x, kid_y, edu_site_in_buffer, edu, tract.name, age)


def __find_edu_ID__(kx, ky, edu_site_in_buffer, edu, tract_name=None, age=None):
    if len(edu_site_in_buffer) == 0:
        raise ValueError(f'no education site within {FAR_BUFFER_M} m of tract {tract_name} for age {age}')

    sx = edu_site_in_buffer.loc[:, 'LATITUDE'].tolist()
    sy = edu_site_in_buffer.loc[:, 'LONGITUDE'].tolist()

    dist = []  # distance list
    for j in range(len(edu_site_in_buffer)):
        d = new_distance(kx, ky, sx[j], sy[j])
        dist.append(d)

    edu_id = edu_site_in_buffer.index
    df_edu_in = pd.DataFrame({'eduID': edu_id, 'Dist': dist}).sort_values(by='Dist')

    sch_AgeDistAccept = [s for s in df_edu_in.eduID if edu.has_room(s)]

    if sch_AgeDistAccept:
        chosen = sch_AgeDistAccept[0]
    else:
        # Every candidate is full: over-capacity assignment is unavoidable.
        chosen = random.choice(edu_site_in_buffer.index)
        edu.fallbacks.append((tract_name, age, chosen))
        logger.warning(f'education capacity fallback: tract {tract_name} age {age} -> {chosen} '
                       f'(all {len(edu_site_in_buffer)} candidate sites full)')
    edu.add(chosen)
    return chosen
