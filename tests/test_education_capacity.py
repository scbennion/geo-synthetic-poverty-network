import geopandas as gpd
import pandas as pd
import pytest
from loguru import logger
from shapely.geometry import Point, box

import src.assign_education_site as aes
from src.assign_education_site import EducationSites, __assign_education_site__

CRS = 'EPSG:4269'
SLC = (-111.9, 40.7)


def _tract(geoid, x0, y0, size=0.01):
    return pd.Series({'geometry': box(x0, y0, x0 + size, y0 + size)}, name=geoid)


def _people(geoid, x0, y0, ages):
    pts = [Point(x0 + 0.002 + 0.0005 * i, y0 + 0.005) for i in range(len(ages))]
    return gpd.GeoDataFrame({'id': [f'{geoid}p{i}' for i in range(len(ages))],
                             'age': ages, 'wp': None}, geometry=pts, crs=CRS)


def _sites(rows):
    df = pd.DataFrame(rows, columns=['eduID', 'x', 'y', 's_age', 'e_age', 'ENROLLMENT', 'count'])
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.x, df.y), crs=CRS)
    gdf['LATITUDE'] = gdf.y
    gdf['LONGITUDE'] = gdf.x
    return gdf.drop(columns=['x', 'y'])


@pytest.fixture
def log_lines():
    lines = []
    sink = logger.add(lines.append, level='WARNING', format='{message}')
    yield lines
    logger.remove(sink)


def _schools():
    # near site fills first; the farther one takes the overflow
    return _sites([
        ('S_near', -111.895, 40.705, 5, 17, 3, 0),
        ('S_far', -111.85, 40.72, 5, 17, 10, 0),
        ('S_hs', -111.89, 40.70, 15, 17, 1, 0),
    ])


def _daycares():
    return _sites([('D1', -111.896, 40.704, 0, 4, 2, 0),
                   ('D2', -111.86, 40.73, 0, 4, 2, 0)])


def _tracts():
    return [_tract('49035000100', -111.90, 40.70), _tract('49035000200', -111.88, 40.70)]


def _run(tracts, ages_by_tract, school, daycare):
    out = []
    for t, ages in zip(tracts, ages_by_tract):
        x0, y0 = t.geometry.bounds[:2]
        people = _people(t.name, x0, y0, ages)
        __assign_education_site__(t, people, school, daycare)
        out.append(people)
    return pd.concat(out)


def test_capacity_persists_across_tracts_without_overfill(log_lines):
    school, daycare = EducationSites(_schools()), EducationSites(_daycares())
    people = _run(_tracts(), [[6, 8, 10, 16, 1], [7, 9, 3, 2]], school, daycare)

    counts = people['wp'].value_counts()
    sites = pd.concat([_schools(), _daycares()]).set_index('eduID')
    assert (counts <= sites.loc[counts.index, 'ENROLLMENT']).all()
    # the counter carried over from tract 1 into tract 2
    assert school.count == {'S_near': 3, 'S_far': 2, 'S_hs': 1}
    assert daycare.count == {'D1': 2, 'D2': 1}
    assert counts.to_dict() == {**school.count, **daycare.count}
    assert school.fallbacks == [] and daycare.fallbacks == [] and log_lines == []


def test_supplied_count_is_starting_enrollment():
    schools = _schools()
    schools.loc[schools.eduID == 'S_near', 'count'] = 3  # already full
    school = EducationSites(schools)
    people = _run(_tracts()[:1], [[6]], school, EducationSites(_daycares()))
    assert people['wp'].iloc[0] == 'S_far'


def test_fallback_only_when_all_full_and_logged(log_lines):
    school, daycare = EducationSites(_schools()), EducationSites(_daycares())
    # 15 school-age kids (5-14, not eligible for S_hs) vs 13 places; 6 daycare kids vs 4 places
    ages = [[6] * 8 + [0, 1, 2], [10] * 7 + [3, 4, 4]]
    people = _run(_tracts(), ages, school, daycare)

    assert len(school.fallbacks) == 2
    assert len(daycare.fallbacks) == 2
    assert len(log_lines) == 4
    assert all('capacity fallback' in m and 'tract 49035000' in m for m in log_lines)
    assert {(t, a) for t, a, _ in school.fallbacks} == {('49035000200', 10)}

    counts = people['wp'].value_counts()
    sites = pd.concat([_schools(), _daycares()]).set_index('eduID')
    over = counts - sites.loc[counts.index, 'ENROLLMENT']
    fallback_sites = pd.Series([e for *_, e in school.fallbacks + daycare.fallbacks]).value_counts()
    # every place above ENROLLMENT is accounted for by a logged fallback
    assert over[over > 0].to_dict() == fallback_sites.to_dict()
    # before the first fallback, every site was filled to capacity
    assert counts['S_near'] >= 3 and counts['S_far'] >= 10 and counts.get('S_hs', 0) == 0


def test_restore_releases_places():
    school = EducationSites(_schools())
    snap = school.snapshot()
    _run(_tracts()[:1], [[6, 7]], school, EducationSites(_daycares()))
    assert school.count['S_near'] == 2
    school.restore(snap)
    assert school.count['S_near'] == 0


def test_buffers_are_metres():
    assert aes.PROJECTED_CRS == 'EPSG:26912'
    assert (aes.NEAR_BUFFER_M, aes.FAR_BUFFER_M) == (11_000, 100_000)
    sites = EducationSites(_schools())
    assert sites.projected_geometry.crs.to_epsg() == 26912
    assert sites.projected_geometry.crs.axis_info[0].unit_name == 'metre'


def _offset_point(t, dx_m, dy_m, corner='ne'):
    """Point dx_m east / dy_m north of a tract corner ('ne' or 'nw'), built in EPSG:26912."""
    x0, _, x1, y1 = t.geometry.bounds
    c = Point(x1 if corner == 'ne' else x0, y1)
    c = gpd.GeoSeries([c], crs=CRS).to_crs(aes.PROJECTED_CRS).iloc[0]
    return Point(c.x + dx_m, c.y + dy_m)


@pytest.mark.parametrize('dx_m, dy_m, near, far', [
    (0, 10_500, True, True),
    (0, 11_500, False, True),
    (10_500, 0, True, True),   # east: about 0.125 deg here, outside the old 0.1-degree buffer
    (0, 99_000, False, True),
    (0, 101_000, False, False),
])
def test_tract_buffers_in_metres(dx_m, dy_m, near, far):
    t = _tract('49035000100', *SLC)
    near_buf, far_buf = aes.tract_buffers(t.geometry)
    p = _offset_point(t, dx_m, dy_m)
    assert near_buf.intersects(p) is near
    assert far_buf.intersects(p) is far


def _site_at(name, t, dx_m, dy_m, corner='ne'):
    p = gpd.GeoSeries([_offset_point(t, dx_m, dy_m, corner)], crs=aes.PROJECTED_CRS).to_crs(CRS).iloc[0]
    return (name, p.x, p.y, 5, 17, 5, 0)


def test_near_pool_excludes_closer_site_outside_11km():
    # ~4 km wide tract, kid at its north-west corner. B (11.5 km north of that corner) is
    # nearer to the kid than A (10.5 km east of the north-east corner, ~14.7 km away),
    # but only A is inside the 11 km near buffer, so the near pool wins and A is chosen.
    t = _tract('49035000100', *SLC, size=0.05)
    rows = [_site_at('A', t, 10_500, 0, 'ne'), _site_at('B', t, 0, 11_500, 'nw')]
    x0, _, _, y1 = t.geometry.bounds
    people = gpd.GeoDataFrame({'age': [8], 'wp': None}, geometry=[Point(x0 + 0.0005, y1 - 0.0005)], crs=CRS)
    __assign_education_site__(t, people, EducationSites(_sites(rows)), EducationSites(_daycares()))
    assert people['wp'].iloc[0] == 'A'

    # control: with A removed, the near pool is empty and B is reached via the 100 km buffer
    people['wp'] = None
    __assign_education_site__(t, people, EducationSites(_sites(rows[1:])), EducationSites(_daycares()))
    assert people['wp'].iloc[0] == 'B'


def test_far_buffer_used_only_when_near_empty():
    t = _tract('49035000100', -111.90, 40.70)
    # 50 km north: outside 11 km, inside 100 km; 150 km: outside both
    rows = [('S_50km', -111.895, 40.71 + 50 / 111.0, 5, 17, 5, 0),
            ('S_150km', -111.895, 40.71 + 150 / 111.0, 5, 17, 5, 0)]
    people = _run([t], [[8]], EducationSites(_sites(rows)), EducationSites(_daycares()))
    assert people['wp'].iloc[0] == 'S_50km'

    rows = [('S_150km', -111.895, 40.71 + 150 / 111.0, 5, 17, 5, 0)]
    with pytest.raises(ValueError, match='no education site'):
        _run([t], [[8]], EducationSites(_sites(rows)), EducationSites(_daycares()))
