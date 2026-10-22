"""Road preprocessing and road-based placement (Agent E). No network access.

Fixtures are small synthetic road grids built in EPSG:26912 (metres) near Salt Lake
City and stored in EPSG:4269 like TIGER/Line, so tests exercise the projections.

    python -m pytest tests/test_roads.py
"""
import importlib.util
import os
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, box

import src.preprocess_data as pp
from src.clean_roads import (clean_road_network, drop_duplicate_lines, label_components,
                             node_lines, snap_vertices)
from src.create_space import (HOME_SPACING_M, OUTPUT_CRS, PLACEMENT_CRS, WORK_SPACING_M,
                              __create_home_location__, __create_work_location__)

REPO = Path(__file__).resolve().parent.parent
ROAD_SCRIPTS = REPO / 'code' / '0-preprocess' / 'prepare-road'
X0, Y0 = 424000.0, 4512000.0   # roughly downtown Salt Lake City in UTM 12N
TRACT_M = 1000.0


def _gdf(rows, crs=PLACEMENT_CRS):
    df = pd.DataFrame(rows, columns=['LINEARID', 'MTFCC', 'geometry'])
    return gpd.GeoDataFrame(df, geometry='geometry', crs=crs)


def _pilot_county():
    """Three 1 km x 1 km tracts in a row and a road grid over them (EPSG:4269).

    Tract 3 has no S1200 road, so its workplace pool relies on local-road endpoints.
    """
    tracts, rows, n = [], [], 0
    for t in range(3):
        x = X0 + t * TRACT_M
        tracts.append({'GEOID': f'4903500{t + 1}00', 'WP_CNT': 7,
                       'geometry': box(x, Y0, x + TRACT_M, Y0 + TRACT_M)})
        for k in range(1, 5):   # local streets, north-south, every 200 m
            xs = x + k * 200
            rows.append((f'L{n}', 'S1400', LineString([(xs, Y0), (xs, Y0 + TRACT_M)])))
            n += 1
        rows.append((f'P{n}', 'S1740', LineString([(x + 50, Y0 + 20), (x + 50, Y0 + 150)])))
        n += 1
    for k in range(1, 5):       # local streets, east-west, across all tracts
        ys = Y0 + k * 200
        rows.append((f'L{n}', 'S1400', LineString([(X0, ys), (X0 + 3 * TRACT_M, ys)])))
        n += 1
    rows.append(('S0', 'S1200', LineString([(X0, Y0 + 500), (X0 + 2 * TRACT_M - 1, Y0 + 500)])))
    tract = gpd.GeoDataFrame(tracts, geometry='geometry', crs=PLACEMENT_CRS).to_crs(OUTPUT_CRS)
    return tract.set_index('GEOID'), _gdf(rows).to_crs(OUTPUT_CRS)


# --- cleaning steps ---------------------------------------------------------

def test_snap_joins_vertices_within_tolerance_only():
    a = LineString([(0, 0), (100, 0)])
    b = LineString([(103, 0), (200, 0)])     # 3 m gap -> snapped
    c = LineString([(300, 0), (400, 0)])
    d = LineString([(420, 0), (500, 0)])     # 20 m gap -> kept apart
    out, keep = snap_vertices([a, b, c, d], tolerance=10)
    assert keep.all()
    assert out[0].coords[-1] == out[1].coords[0] == (100.0, 0.0)   # earlier vertex is the anchor
    assert out[2].coords[-1] != out[3].coords[0]


def test_snap_drops_lines_that_collapse():
    out, keep = snap_vertices([LineString([(0, 0), (100, 0)]), LineString([(0, 1), (2, 1)])], 10)
    assert list(keep) == [True, False]


def test_break_splits_crossings_and_keeps_attributes():
    roads = _gdf([('A', 'S1400', LineString([(0, 50), (100, 50)])),
                  ('B', 'S1200', LineString([(50, 0), (50, 100)]))])
    noded = node_lines(roads)
    assert len(noded) == 4
    assert sorted(noded.LINEARID) == ['A', 'A', 'B', 'B']
    assert (noded[noded.LINEARID == 'B'].MTFCC == 'S1200').all()
    assert np.isclose(noded.length.sum(), 200)


def test_duplicates_dropped_within_road_class_first_wins():
    line = LineString([(0, 0), (100, 0)])
    roads = _gdf([('A', 'S1400', line), ('B', 'S1400', line.reverse()),
                  ('C', 'S1400', LineString([(0, 10), (100, 10)])),
                  ('D', 'S1200', LineString([(0, 0), (50, 0)]))])   # overlaps half of A
    cleaned = drop_duplicate_lines(node_lines(roads))
    assert sorted(cleaned.LINEARID) == ['A', 'A', 'C', 'D']           # A split at D's end
    assert np.isclose(cleaned[cleaned.MTFCC == 'S1400'].length.sum(), 200)
    assert np.isclose(cleaned[cleaned.MTFCC == 'S1200'].length.sum(), 50)
    # GRASS-like: one feature per geometry regardless of class
    grass_like = drop_duplicate_lines(node_lines(roads, class_column=None), class_column=None)
    assert sorted(grass_like.LINEARID) == ['A', 'A', 'C']
    dup = _gdf([('A', 'S1400', line), ('B', 'S1400', line.reverse())])
    assert list(drop_duplicate_lines(dup).LINEARID) == ['A']


def test_components_label_connected_groups():
    roads = _gdf([('A', 'S1400', LineString([(0, 0), (10, 0)])),
                  ('B', 'S1400', LineString([(10, 0), (10, 10)])),
                  ('C', 'S1400', LineString([(50, 50), (60, 50)]))])
    comp = label_components(roads)
    assert comp[0] == comp[1] != comp[2]


def test_clean_road_network_end_to_end():
    _, roads = _pilot_county()
    cleaned = clean_road_network(roads)
    assert cleaned.crs == roads.crs
    assert list(cleaned.columns) == ['LINEARID', 'MTFCC', 'comp', 'geometry']
    assert set(cleaned.MTFCC) == {'S1400', 'S1740', 'S1200'}
    assert len(cleaned) > len(roads)                    # split at crossings
    assert cleaned.geom_type.eq('LineString').all()
    total = lambda g: g.to_crs(PLACEMENT_CRS).length.sum()
    assert np.isclose(total(cleaned), total(roads), rtol=1e-6)
    # the grid is one network; each private road is its own dead-end component
    assert cleaned['comp'].nunique() == 4


def test_clean_requires_lon_lat_crs():
    line = [LineString([(0, 0), (1, 1)])]
    with pytest.raises(ValueError):
        clean_road_network(gpd.GeoDataFrame({'MTFCC': ['S1400']}, geometry=line))
    with pytest.raises(ValueError):
        clean_road_network(gpd.GeoDataFrame({'MTFCC': ['S1400']}, geometry=line, crs=PLACEMENT_CRS))


def test_clean_keeps_unsnapped_coordinates_exactly():
    # roads that follow tract boundaries must still coincide with them after cleaning
    _, roads = _pilot_county()
    cleaned = clean_road_network(roads)
    before = {tuple(c) for c in roads.get_coordinates().to_numpy()}
    after = {tuple(c) for c in cleaned.get_coordinates().to_numpy()}
    assert before <= after   # no vertex moved; only crossing nodes were added


# --- file round trip and drivers ---------------------------------------------

def test_process_interim_road_data_writes_cleaned_zip(tmp_path):
    _, roads = _pilot_county()
    (tmp_path / 'interim' / 'road').mkdir(parents=True)
    roads.to_file(tmp_path / 'interim' / 'road' / 'UT_road.shp.zip')
    out = pp.process_interim_road_data('UT', interim_data_path=str(tmp_path / 'interim'),
                                       processed_data_path=str(tmp_path / 'processed'))
    assert out == str(tmp_path / 'processed' / 'road' / 'UT_road_cleaned.shp.zip')
    back = gpd.read_file(out)
    assert back.crs.to_epsg() == 4269
    assert {'LINEARID', 'MTFCC', 'comp'} <= set(back.columns)


def test_process_interim_road_data_missing_input(tmp_path):
    with pytest.raises(FileNotFoundError):
        pp.process_interim_road_data('UT', interim_data_path=str(tmp_path),
                                     processed_data_path=str(tmp_path))


def test_download_filters_counties(tmp_path, monkeypatch):
    _, roads = _pilot_county()
    listed = ['tl_2020_49035_roads.zip', 'tl_2020_49049_roads.zip']
    fetched = []
    monkeypatch.setattr(pp, 'get_road_file_names', lambda url, fips: listed)

    def fake_download(url, path, verify_ssl=True):
        assert verify_ssl
        fetched.append(url)
        roads.to_file(path + '.shp.zip')   # GDAL picks the zipped-shapefile writer by suffix
        os.replace(path + '.shp.zip', path)
        return True
    monkeypatch.setattr(pp, 'download_file', fake_download)
    out = pp.download_and_prepare_road_data('49', 'UT', raw_data_path=str(tmp_path / 'raw'),
                                            interim_data_path=str(tmp_path / 'interim'),
                                            counties=['035'], output_name='UT_c035')
    assert fetched == ['https://www2.census.gov/geo/tiger/TIGER2020/ROADS/tl_2020_49035_roads.zip']
    assert out.endswith('road/UT_c035_road.shp.zip') and len(gpd.read_file(out)) == len(roads)


def test_download_failure_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(pp, 'get_road_file_names', lambda url, fips: ['tl_2020_49035_roads.zip'])
    monkeypatch.setattr(pp, 'download_file', lambda url, path, verify_ssl=True: False)
    with pytest.raises(RuntimeError):
        pp.download_and_prepare_road_data('49', 'UT', raw_data_path=str(tmp_path),
                                          interim_data_path=str(tmp_path))


def test_download_file_verifies_tls(tmp_path, monkeypatch):
    seen = {}

    class Resp:
        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size):
            yield b'data'

    def fake_get(url, stream, verify, timeout):
        seen['verify'] = verify
        return Resp()
    monkeypatch.setattr(pp.requests, 'get', fake_get)
    target = tmp_path / 'f.zip'
    assert pp.download_file('https://example.invalid/f.zip', str(target))
    assert seen['verify'] is True and target.read_bytes() == b'data'


@pytest.mark.parametrize('script', ['download_process_roads.py', 'clean_roads.py'])
def test_road_scripts_import_without_grass(script):
    spec = importlib.util.spec_from_file_location(script[:-3], ROAD_SCRIPTS / script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)   # fails on a bad import name or a GRASS import
    assert callable(module.main)


def test_no_tls_suppression_left_in_road_path():
    for path in [REPO / 'src' / 'preprocess_data.py', *ROAD_SCRIPTS.glob('*.py')]:
        text = path.read_text()
        assert 'InsecureRequestWarning' not in text
        assert 'GRASSBIN' not in text


# --- placement ----------------------------------------------------------------

def test_every_pilot_tract_has_home_and_workplace_candidates():
    tracts, roads = _pilot_county()
    roads = clean_road_network(roads)
    for _, tract in tracts.iterrows():
        homes = __create_home_location__(tract, 25, roads)
        works = __create_work_location__(tract, roads)
        assert len(homes) == 25 and homes.notna().all()
        assert len(works) == tract.WP_CNT and works.notna().all()
        assert homes.within(tract.geometry.buffer(1e-9)).all()
        assert works.within(tract.geometry.buffer(1e-9)).all()


def _spacings(points, crs):
    xy = np.unique(np.round(gpd.GeoSeries(list(points), crs=crs).to_crs(PLACEMENT_CRS)
                            .get_coordinates().to_numpy(), 6), axis=0)
    return np.diff(np.sort(xy[:, 0]))


def test_home_and_work_points_are_spaced_in_metres():
    # one straight 1010 m east-west road per class, well inside a 2 km tract
    tract = gpd.GeoDataFrame({'WP_CNT': [5000]}, index=['49035000100'], crs=PLACEMENT_CRS,
                             geometry=[box(X0, Y0, X0 + 2000, Y0 + 2000)]).to_crs(OUTPUT_CRS).iloc[0]
    roads = _gdf([('L', 'S1400', LineString([(X0 + 500, Y0 + 1000), (X0 + 1510, Y0 + 1000)])),
                  ('S', 'S1200', LineString([(X0 + 500, Y0 + 1500), (X0 + 1510, Y0 + 1500)]))]
                 ).to_crs(OUTPUT_CRS)

    homes = __create_home_location__(tract, 5000, roads)
    assert homes.crs == OUTPUT_CRS
    home_gaps = _spacings(homes, OUTPUT_CRS)
    assert len(home_gaps) == 1000 // HOME_SPACING_M - 1      # 20 points at 50..1000 m
    assert np.allclose(home_gaps, HOME_SPACING_M, atol=0.01)
    # the old 0.0005-degree step would give ~42 m along an east-west road at 40.7 N
    assert not np.isclose(home_gaps.mean(), 0.0005 * 111320 * np.cos(np.radians(40.75)), atol=1)

    works = __create_work_location__(tract, roads)
    assert works.crs == OUTPUT_CRS
    lat = gpd.GeoSeries(list(works), crs=OUTPUT_CRS).to_crs(PLACEMENT_CRS).y
    work_gaps = _spacings(works[np.isclose(lat, Y0 + 1500, atol=0.01)], OUTPUT_CRS)
    assert np.allclose(work_gaps, WORK_SPACING_M, atol=0.01)


# --- optional check on real prepared data --------------------------------------

def test_real_pilot_county_candidate_pools():
    """Runs only when GSPN_DATA_DIR holds the Utah road file and a 2020 tract file."""
    from src.settings import PROCESSED_DATA_DIR, RAW_DATA_DIR
    road_path = os.path.join(PROCESSED_DATA_DIR, 'road', 'UT_road_cleaned.shp.zip')
    tract_candidates = [os.path.join(PROCESSED_DATA_DIR, 'census', 'ut-tracts-demo-work.shp.zip'),
                        os.path.join(RAW_DATA_DIR, 'census', 'tl_2020_49_tract.zip')]
    tract_path = next((p for p in tract_candidates if os.path.exists(p)), None)
    if not os.path.exists(road_path) or tract_path is None:
        pytest.skip('real Utah road/tract data not present under GSPN_DATA_DIR')
    tracts = gpd.read_file(tract_path)
    tracts = tracts[tracts.GEOID.str.startswith('49035')]
    if 'DP1_0001C' in tracts:
        tracts = tracts[tracts.DP1_0001C > 0]
    else:
        tracts = tracts[tracts.ALAND > 0]
    roads = gpd.read_file(road_path, bbox=tuple(tracts.total_bounds))
    tracts = tracts.to_crs(roads.crs).set_index('GEOID').assign(WP_CNT=1)
    empty = []
    for geoid, tract in tracts.iterrows():
        try:
            __create_home_location__(tract, 1, roads)
            __create_work_location__(tract, roads)
        except ValueError:
            empty.append(geoid)
    assert not empty, f'tracts with an empty candidate pool: {empty}'
