import geopandas as gpd
import pandas as pd
import numpy as np
from shapely import MultiLineString, Point, ops, LineString

# Utah-specific: NAD83 / UTM zone 12N (metres). Roads are projected to this CRS so
# that the placement spacing below is in metres, then points go back to OUTPUT_CRS.
PLACEMENT_CRS = 'EPSG:26912'
OUTPUT_CRS = 'EPSG:4269'
# paper (Jiang et al. 2024, Steps 1-2): ~50 m between homes, ~20 m between workplaces
HOME_SPACING_M = 50
WORK_SPACING_M = 20


def __points_along__(lines, spacing):
    '''
    Points every `spacing` metres along each line (starting at `spacing`), computed in
    PLACEMENT_CRS and returned as a flat GeoSeries in OUTPUT_CRS.
    :param lines: GeoSeries of (Multi)LineStrings with a CRS
    :param spacing: distance between points in metres
    '''
    projected = lines.to_crs(PLACEMENT_CRS)
    points = [x.interpolate(seg) for x in projected for seg in np.arange(spacing, x.length, spacing)]
    return gpd.GeoSeries(points, crs=PLACEMENT_CRS).to_crs(OUTPUT_CRS)

def __hash_geom__(g):
    '''
    Hash geometric, create space, shapely geometries are not hashable, here is my hash function to check the duplicates
    :param g:
    :return: coordinates (latitude, longitude)
    '''
    #print("Get the lat and long of the road segment and output to tuple")
    if g.geom_type == 'MultiLineString':
        #print("MultiLineString")
        #print(g.geoms)
        cord_list = []
        for line in g.geoms:
            for lat,lon in line.coords[:]:
                #print((round(lat,6),round(lon,6)))
                cord_list.append((round(lat,6),round(lon,6)))
        #print(cord_list)
        cord_tuple = tuple(item for item in cord_list)
        #print("Tuple")
        #print(cord_tuple)
        return tuple(item for item in cord_list)
    else:
        #print("Line")
        #print(tuple((round(lat,6),round(lon,6)) for lat,lon in g.coords[:]))
        return tuple((round(lat,6),round(lon,6)) for lat,lon in g.coords[:]) #shaply older version
        #return tuple((round(lat,6),round(lon,6)) for lat,lon in g.geoms) #shapely 2.0 or later version


def __create_home_location__(tract, household_count, road, rng=None):
    '''
    creat home loaction
    :param tract: row of census tract
    :param hcnt: hhold count
    :param road:
    :return:
    '''


    # Find roads intersecting with census tract geometry
    #print("- Step 1.3 Creating home_location-")
    mask = road.intersects(tract.geometry)
    home_mask = mask & road['MTFCC'].str.contains(
        'S1400|S1740')  # * Home Road: S1400 Local Neighborhood Road, Rural Road, City Street, S1740 Private Road for service vehicles (logging, oil fields, ranches, etc.)
    home_roads = road[home_mask].intersection(tract.geometry)
    home_roads = home_roads[home_roads.geom_type.isin(['LineString', 'MultiLineString'])]
    home_roads = home_roads[~home_roads.apply(
        __hash_geom__).duplicated()]  # remove the duplicate lat and long by returning boolean Series denoting duplicate rows (using .duplicated()).

    # Interpolate points along home roads, every HOME_SPACING_M metres
    flattened_points = __points_along__(home_roads, HOME_SPACING_M)

    # Sample home locations
    sampled_homes = flattened_points.sample(n=household_count, replace=True, random_state=rng).reset_index(drop=True)
    sampled_homes.index = tract.name + 'h' + sampled_homes.index.to_series().astype(str)

    return gpd.GeoSeries(sampled_homes)


def __create_work_location__(tract, road, rng=None):
    '''
    Creates work place on a primary road, secondary road and intersection of home road.

    :param tract: GeoDataFrame containing census tract data.
    :param road: GeoDataFrame containing road data.
    :return: GeoSeries representing work locations.
    '''

    # from shapely import MultiLineString, Point, ops, LineString
    # primary road, secondary road
    #print("- Step 2.2 Creating Work location on Road Networks-")
    mask = road.intersects(tract.geometry)  # get the road with in the census tract
    work_mask = mask & road.MTFCC.str.contains('S1200')  # * Work Road: S1100 Primary Road; S1200 Secondary Road

    work_road = road[work_mask].intersection(tract.geometry)  # get the geometry of work road
    work_road = work_road[work_road.geom_type.isin(['LinearRing', 'LineString', 'MultiLineString'])]
    work_road = work_road[~work_road.apply(
        __hash_geom__).duplicated()]  # remove the duplicate lat and long by returning boolean Series denoting duplicate rows (using .duplicated()).

    # Interpolate points along work roads, every WORK_SPACING_M metres
    interpolated_points = __points_along__(work_road, WORK_SPACING_M)

    # home road interections
    home_mask = mask & road['MTFCC'].str.contains(
        'S1400|S1740')  # * Home Road: S1400 Local Neighborhood Road, Rural Road, City Street, S1740 Private Road for service vehicles (logging, oil fields, ranches, etc.)
    home_roads = road[home_mask].intersection(tract.geometry)
    home_roads = home_roads[home_roads.geom_type.isin(['LineString', 'MultiLineString'])]
    home_roads = home_roads[~home_roads.apply(__hash_geom__).duplicated()]

    intersection_points = home_roads.apply(
        lambda x: Point(x.coords[0]) if type(x) != MultiLineString else Point(x.geoms[0].coords[0]))
    intersection_points = gpd.GeoSeries(intersection_points, crs=home_roads.crs).to_crs(OUTPUT_CRS)

    work_place = pd.DataFrame()
    # print(wrk_point)
    if len(interpolated_points) > 0:
        flattened_points = interpolated_points
        # temp = wrk_point.unstack().dropna().reset_index(drop=True)
        work_place = pd.concat([flattened_points, intersection_points])

    else:
        work_place = intersection_points

    work_place = work_place.sample(n=tract.WP_CNT, replace=True, random_state=rng).reset_index(drop=True)
    work_place.index = tract.name + 'w' + work_place.index.to_series().astype(str)
    # print("workplace")
    # print(wrk_place)'

    return gpd.GeoSeries(work_place)