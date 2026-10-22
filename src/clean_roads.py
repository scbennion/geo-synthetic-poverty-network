"""Pure-Python road-network cleaning (replaces the former GRASS GIS step).

The GRASS script this replaces ran, in a lon/lat (EPSG:4326) location:

    v.clean tool=snap,break,rmdupl,rmsa threshold=0.0001,0.0,0.0,0.0
    v.net.components method=weak

``clean_road_network`` reproduces the first three tools and the component
labelling with shapely/scipy:

1. snap   -- vertices within ``SNAP_TOLERANCE_DEG`` (0.0001, the GRASS threshold)
             of an earlier vertex are moved onto it (greedy anchors in input
             order). Work is done in the input lon/lat CRS, as GRASS did, so
             vertices that are not snapped keep their exact TIGER coordinates
             and still coincide with TIGER tract boundaries.
2. break  -- lines are split at every crossing and shared vertex
             (``shapely.unary_union`` noding); each piece keeps the attributes
             of the first input line of each road class (``MTFCC``) that covers it.
3. rmdupl -- duplicate pieces (identical geometry, either direction) of the same
             road class are dropped, keeping the first.
4. weak components -- each piece gets a ``comp`` id; pieces sharing an end node
             are in the same component. Components are labelled, not filtered.

Differences from GRASS (see CHANGELOG_vs_jiang2024.md):
- GRASS ran in EPSG:4326 (TIGER is EPSG:4269, read with the -o override);
  here the TIGER CRS is kept. 0.0001 degrees is about 8.5 m east-west and
  11.1 m north-south in Utah;
- only vertex-to-vertex snapping is done; GRASS additionally inserts anchor
  vertices into segments that pass within the threshold;
- ``rmsa`` (remove small angles at nodes) is not implemented;
- duplicates are removed per road class: an edge carried by both an S1200 and
  an S1400 feature (TIGER has such coincident features) stays once in each class, so it remains a
  candidate for both workplaces and homes. GRASS keeps only the first feature
  (pass ``class_column=None`` for that behaviour);
- component ids are arbitrary integers, not GRASS category numbers.
"""
import numpy as np
import pandas as pd
import geopandas as gpd
import shapely
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

# GRASS v.clean snap threshold, in degrees of the lon/lat input CRS
SNAP_TOLERANCE_DEG = 0.0001
# max distance (CRS units; ~1 cm in degrees) between a noded piece and its source line
_MATCH_TOLERANCE = 1e-7
KEEP_COLUMNS = ["LINEARID", "MTFCC"]


def _explode_lines(gdf):
    """One LineString per row; drops empty and non-line geometries."""
    gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()]
    gdf = gdf.explode(index_parts=False, ignore_index=True)
    return gdf[gdf.geom_type == "LineString"].reset_index(drop=True)


def snap_vertices(geoms, tolerance):
    """Snap every vertex to an anchor vertex within ``tolerance`` (CRS units).

    Vertices are visited in input order; an unsnapped vertex becomes an anchor and
    captures all still-unsnapped vertices within ``tolerance`` of it. Consecutive
    repeated vertices are removed and lines that collapse to a point are dropped.

    Returns (snapped geometries as an object array, boolean keep mask).
    """
    geoms = np.asarray(geoms, dtype=object)
    coords, line_idx = shapely.get_coordinates(geoms, return_index=True)
    if tolerance > 0 and len(coords):
        uniq, inverse = np.unique(coords, axis=0, return_inverse=True)
        inverse = inverse.ravel()
        # keep input order: unique point k is first seen at position first[k]
        first = np.full(len(uniq), len(coords), dtype=np.int64)
        np.minimum.at(first, inverse, np.arange(len(coords)))
        pairs = cKDTree(uniq).query_pairs(tolerance, output_type="ndarray")
        target = np.arange(len(uniq))
        if len(pairs):
            n = len(uniq)
            adj = coo_matrix(
                (np.ones(2 * len(pairs), dtype=bool),
                 (np.concatenate([pairs[:, 0], pairs[:, 1]]),
                  np.concatenate([pairs[:, 1], pairs[:, 0]]))),
                shape=(n, n)).tocsr()
            assigned = np.zeros(n, dtype=bool)
            involved = np.unique(pairs)
            for k in involved[np.argsort(first[involved], kind="stable")]:
                if assigned[k]:
                    continue
                assigned[k] = True
                nbrs = adj.indices[adj.indptr[k]:adj.indptr[k + 1]]
                nbrs = nbrs[~assigned[nbrs]]
                target[nbrs] = k
                assigned[nbrs] = True
        coords = uniq[target[inverse]]

    out = np.empty(len(geoms), dtype=object)
    keep = np.zeros(len(geoms), dtype=bool)
    splits = np.flatnonzero(np.diff(line_idx)) + 1
    starts = np.concatenate([[0], splits])
    for start, pts in zip(starts, np.split(coords, splits)):
        if len(pts) == 0:
            continue
        i = line_idx[start]
        step = np.any(pts[1:] != pts[:-1], axis=1)
        pts = pts[np.concatenate([[True], step])]
        if len(pts) >= 2:
            out[i] = shapely.LineString(pts)
            keep[i] = True
    return out, keep


def node_lines(gdf, match_tolerance=_MATCH_TOLERANCE, class_column="MTFCC"):
    """Split lines at all crossings and shared vertices ("break").

    Overlapping parts are merged by the noding. Each output piece takes the
    attributes of the first (lowest-index) input line covering it -- one row per
    distinct ``class_column`` value among the covering lines, or a single row if
    ``class_column`` is None.
    """
    if gdf.empty:
        return gdf.copy()
    noded = shapely.unary_union(gdf.geometry.values)
    pieces = shapely.get_parts(noded)
    pieces = pieces[shapely.get_type_id(pieces) == 1]  # LineString
    pieces = pieces[~shapely.is_empty(pieces) & (shapely.length(pieces) > 0)]
    mid = shapely.line_interpolate_point(pieces, 0.5, normalized=True)
    tree = shapely.STRtree(gdf.geometry.values)
    piece_i, line_i = tree.query(mid, predicate="dwithin", distance=match_tolerance)
    # first matching input line per piece (and class); query results are not ordered
    match = pd.DataFrame({"piece": piece_i, "line": line_i}).sort_values(["piece", "line"])
    keys = ["piece"]
    if class_column is not None and class_column in gdf.columns:
        match["cls"] = gdf[class_column].to_numpy()[match["line"].to_numpy()]
        keys.append("cls")
    match = match.drop_duplicates(keys)
    out = gdf.iloc[match["line"].to_numpy()].copy()
    out = out.set_geometry(gpd.GeoSeries(pieces[match["piece"].to_numpy()], index=out.index, crs=gdf.crs))
    return out.reset_index(drop=True)


def drop_duplicate_lines(gdf, class_column="MTFCC"):
    """Drop rows whose geometry duplicates an earlier row ("rmdupl"), either direction.

    With ``class_column`` set, only duplicates within the same class are dropped.
    """
    key = pd.DataFrame({"geom": shapely.to_wkb(shapely.normalize(gdf.geometry.values))})
    if class_column is not None and class_column in gdf.columns:
        key["cls"] = gdf[class_column].to_numpy()
    return gdf[~key.duplicated().to_numpy()].reset_index(drop=True)


def label_components(gdf, node_tolerance=None):
    """Weakly connected component id per line, via shared end nodes.

    End nodes are compared exactly (after snapping/noding they coincide); pass
    ``node_tolerance`` (CRS units) to round them first.
    """
    if gdf.empty:
        return np.array([], dtype=np.int64)
    starts = shapely.get_coordinates(shapely.get_point(gdf.geometry.values, 0))
    ends = shapely.get_coordinates(shapely.get_point(gdf.geometry.values, -1))
    nodes = np.vstack([starts, ends])
    if node_tolerance:
        nodes = np.round(nodes / node_tolerance) * node_tolerance
    _, node_id = np.unique(nodes, axis=0, return_inverse=True)
    node_id = node_id.ravel()
    n_lines = len(gdf)
    u, v = node_id[:n_lines], node_id[n_lines:]
    n_nodes = node_id.max() + 1
    graph = coo_matrix((np.ones(n_lines), (u, v)), shape=(n_nodes, n_nodes))
    _, node_comp = connected_components(graph, directed=False)
    return node_comp[u].astype(np.int64)


def clean_road_network(roads, snap_tolerance=SNAP_TOLERANCE_DEG,
                       keep_columns=KEEP_COLUMNS, class_column="MTFCC"):
    """Snap, break, de-duplicate and label components of a road GeoDataFrame.

    ``roads`` must be in a geographic (lon/lat) CRS such as TIGER's EPSG:4269;
    ``snap_tolerance`` is in degrees. Returns a GeoDataFrame with
    ``keep_columns`` + ``comp`` + geometry in the same CRS. ``class_column=None``
    de-duplicates across road classes (GRASS-like, first feature wins).
    """
    if roads.crs is None or not roads.crs.is_geographic:
        raise ValueError(f"expected lon/lat roads (TIGER/Line is EPSG:4269), got CRS {roads.crs}")
    cols = [c for c in keep_columns if c in roads.columns]
    gdf = _explode_lines(roads[cols + [roads.geometry.name]])

    snapped, keep = snap_vertices(gdf.geometry.values, snap_tolerance)
    gdf = gdf[keep].copy()
    gdf = gdf.set_geometry(gpd.GeoSeries(snapped[keep], index=gdf.index, crs=roads.crs))
    gdf = gdf.reset_index(drop=True)

    gdf = node_lines(gdf, class_column=class_column)
    gdf = drop_duplicate_lines(gdf, class_column=class_column)
    gdf["comp"] = label_components(gdf)
    return gdf[cols + ["comp", gdf.geometry.name]]
