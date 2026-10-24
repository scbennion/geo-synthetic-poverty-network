"""Stream a county or city-boundary subset without changing source files."""

import csv
import hashlib
import json
import re
import shutil
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from pathlib import Path


NETWORK_TYPES = ("household", "work", "school", "daycare")
POPULATION_COLUMNS = (
    "fid", "geom", "id", "age", "gender", "assigned", "hhold", "htype",
    "wp", "urban", "long", "lat",
)
SITE_COLUMNS = ("wp", "site_type", "long", "lat", "geom", "fid", "location_status")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_person_id(value):
    """Return the encoded home county; the full identifier must be valid."""
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{11}i[0-9]+", value):
        raise ValueError(f"Invalid person ID: {value!r}")
    return value[:5]


def canonical_edge(source, target):
    if source == target:
        raise ValueError(f"Self edge: {source}")
    return tuple(sorted((source, target)))


def iter_network(path, network_type):
    """Read the supplied state formats; a one-cell adjacency row is an isolate."""
    if network_type not in NETWORK_TYPES:
        raise ValueError(f"Unknown network type: {network_type}")
    with Path(path).open(newline="", encoding="utf-8") as stream:
        rows = csv.reader(stream)
        if network_type == "work" and next(rows, None) != ["", "source", "target"]:
            raise ValueError(f"Unexpected work-network header in {path}")
        start = 2 if network_type == "work" else 1
        for line, row in enumerate(rows, start):
            if not row or (network_type == "work" and len(row) != 3):
                raise ValueError(f"Malformed network row: {path}:{line}")
            people = row[1:] if network_type == "work" else row
            for value in people:
                parse_person_id(value)
            for neighbor in people[1:]:
                yield people[0], neighbor


def read_population(path):
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        columns = ", ".join(f'"{name}"' for name in POPULATION_COLUMNS)
        for row in db.execute(f"SELECT {columns} FROM ut_population ORDER BY fid"):
            yield dict(row)


def csv_value(value):
    return value.hex() if isinstance(value, bytes) else value


def write_rows(path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_value(row.get(key)) for key in columns})
            count += 1
    return {"rows": count, "sha256": sha256(path)}


def load_boundary(path):
    """Require an explicit CRS: this pipeline tests NAD83 home coordinates."""
    from shapely.geometry import Point, shape
    from shapely.prepared import prep
    from shapely.ops import unary_union

    document = json.loads(Path(path).read_text())
    crs = document.get("crs", {}).get("properties", {}).get("name", "")
    if crs not in ("EPSG:4269", "urn:ogc:def:crs:EPSG::4269"):
        raise ValueError("Boundary must explicitly declare EPSG:4269 (NAD83)")
    if document.get("type") != "FeatureCollection" or not document.get("features"):
        raise ValueError("Boundary must be a nonempty GeoJSON FeatureCollection")
    shapes = [shape(feature["geometry"]) for feature in document["features"]]
    if any(s.geom_type not in ("Polygon", "MultiPolygon") or not s.is_valid for s in shapes):
        raise ValueError("Boundary must contain valid polygons")
    geometry = prep(unary_union(shapes))

    def contains(row):
        if row["long"] is None or row["lat"] is None:
            raise ValueError(f"Missing home coordinates for {row['id']}")
        return geometry.covers(Point(row["long"], row["lat"]))

    return contains


def collect_population(path, county_code, contains, home_tracts=None):
    selected, all_ids, exceptions = {}, set(), []
    county_households = Counter()
    for row in read_population(path):
        person_id = row["id"]
        if person_id is None:
            exceptions.append({
                "source": "ut_population.gpkg", "record": row["fid"],
                "kind": "missing_person_id",
                "detail": json.dumps({k: csv_value(v) for k, v in row.items()}, sort_keys=True),
            })
            continue
        county = parse_person_id(person_id)
        if person_id in all_ids:
            raise ValueError(f"Duplicate population ID: {person_id}")
        all_ids.add(person_id)
        if county != county_code:
            continue
        if not row["hhold"]:
            raise ValueError(f"Missing household for {person_id}")
        county_households[row["hhold"]] += 1
        if (home_tracts is None or person_id[:11] in home_tracts) and (contains is None or contains(row)):
            selected[person_id] = row
    if not selected:
        raise ValueError("Selection contains no residents")
    selected_households = Counter(row["hhold"] for row in selected.values())
    for household, count in selected_households.items():
        if count != county_households[household]:
            raise ValueError(f"Boundary splits household {household}; inspect inconsistent home points")
    return selected, all_ids, exceptions


def household_rows(people):
    households = {}
    for row in people.values():
        key = row["hhold"]
        attributes = {name: row[name] for name in ("hhold", "htype", "long", "lat")}
        if key not in households:
            households[key] = {**attributes, "member_count": 0}
        if any(households[key][name] != value for name, value in attributes.items()):
            raise ValueError(f"Inconsistent household attributes: {key}")
        households[key]["member_count"] += 1
    return [households[key] for key in sorted(households)]


def site_rows(path, people):
    kinds = {"w": "workplace", "s": "school", "d": "daycare"}
    sites = {}
    for row in people.values():
        key = row["wp"]
        if key is None:
            continue
        match = re.fullmatch(r"[0-9]{11}([wsd])(?:[0-9]+|None|NotFound)", key)
        if not match:
            raise ValueError(f"Unrecognized daytime ID: {key!r}")
        kind = kinds[match[1]]
        sites[key] = {
            "wp": key, "site_type": kind,
            "location_status": "unavailable_in_source" if kind != "workplace" else "not_found_in_source",
        }
    # A single pass avoids 10 million temporary workplace nodes or a new source index.
    matched = set()
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        for row in db.execute("SELECT fid, geom, wp, long, lat FROM ut_workplace"):
            key = row["wp"]
            if key in sites:
                if key in matched:
                    raise ValueError(f"Duplicate workplace ID: {key}")
                matched.add(key)
                sites[key].update(dict(row))
                sites[key]["location_status"] = (
                    "available" if row["long"] is not None and row["lat"] is not None
                    else "missing_coordinates"
                )
    return [sites[key] for key in sorted(sites)]


def extract_county(input_dir, output_dir, county_code="49049", *, place_boundary=None, area_name=None, home_tracts=None):
    """Create an atomic, auditable resident subset plus its direct boundary ties.

    No graph is re-generated. City selection uses synthetic home points, not the
    destination tract in wp. Boundary neighbors are retained separately and are
    not expanded recursively or imported into Neo4j by default.
    """
    input_dir, output_dir = Path(input_dir).resolve(), Path(output_dir).resolve()
    if output_dir.exists():
        raise FileExistsError(output_dir)
    if not re.fullmatch(r"49[0-9]{3}", county_code):
        raise ValueError("Expected a five-digit Utah county FIPS code")
    sources = ["ut_population.gpkg", "ut_workplace.gpkg"] + [
        f"social_networks/ut_{kind}_network.csv" for kind in NETWORK_TYPES
    ]
    source_hashes = {name: sha256(input_dir / name) for name in sources}
    selection = {"county_fips": county_code, "area_name": area_name or county_code,
                 "rule": "encoded home county"}
    if home_tracts is not None:
        home_tracts = sorted(set(home_tracts))
        if not home_tracts or any(not re.fullmatch(r"[0-9]{11}", tract) or
                                 not tract.startswith(county_code) for tract in home_tracts):
            raise ValueError("Home tracts must be eleven-digit GEOIDs in the selected county")
        selection.update(home_tracts=home_tracts, rule="encoded home tract in explicit tract list")
    contains = None
    if place_boundary is not None:
        contains = load_boundary(place_boundary)
        selection.update(boundary_sha256=sha256(place_boundary), boundary_crs="EPSG:4269",
                         rule=selection["rule"] + " AND boundary covers synthetic home point")
    fingerprint = json.dumps({"source_sha256": source_hashes, "selection": selection}, sort_keys=True)
    dataset_id = hashlib.sha256(fingerprint.encode()).hexdigest()[:24]
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}-", dir=output_dir.parent))
    try:
        people, all_ids, exceptions = collect_population(
            input_dir / "ut_population.gpkg", county_code, contains, home_tracts)
        files = {}

        def export(name, columns, rows):
            files[name] = write_rows(staging / name, columns, rows)

        export("population.csv", POPULATION_COLUMNS, (people[key] for key in sorted(people)))
        households = household_rows(people)
        export("households.csv", ("hhold", "htype", "member_count", "long", "lat"), households)
        sites = site_rows(input_dir / "ut_workplace.gpkg", people)
        export("sites.csv", SITE_COLUMNS, sites)
        outside_ids, network_counts = set(), {}
        for kind in NETWORK_TYPES:
            internal, boundary = set(), set()
            duplicates = 0
            for source, target in iter_network(input_dir / f"social_networks/ut_{kind}_network.csv", kind):
                if source not in all_ids or target not in all_ids:
                    raise ValueError(f"Unknown population endpoint in {kind}: {source}, {target}")
                edge = canonical_edge(source, target)
                source_inside, target_inside = source in people, target in people
                if not (source_inside or target_inside):
                    continue
                collection = internal if source_inside and target_inside else boundary
                duplicates += edge in collection
                collection.add(edge)
                if collection is boundary:
                    outside_ids.add(target if source_inside else source)
            for directory, edges in (("networks", internal), ("boundary_networks", boundary)):
                export(f"{directory}/{kind}.csv", ("source", "target"),
                       ({"source": a, "target": b} for a, b in sorted(edges)))
            network_counts[kind] = {"internal": len(internal), "boundary": len(boundary),
                                    "duplicate_entries_removed": duplicates}
        external = (row for row in read_population(input_dir / "ut_population.gpkg") if row["id"] in outside_ids)
        export("boundary_people.csv", POPULATION_COLUMNS, external)
        if files["boundary_people.csv"]["rows"] != len(outside_ids):
            raise ValueError("Boundary population is incomplete")
        export("exceptions.csv", ("source", "record", "kind", "detail"), exceptions)
        if place_boundary is not None:
            shutil.copyfile(place_boundary, staging / "boundary.geojson")
            files["boundary.geojson"] = {"sha256": sha256(staging / "boundary.geojson")}
        # Catch concurrent source edits; never publish a mixed-source extract.
        if any(sha256(input_dir / name) != digest for name, digest in source_hashes.items()):
            raise ValueError("Source files changed during extraction")
        counts = {"population": len(people), "households": len(households),
                  "sites": dict(Counter(row["site_type"] for row in sites)),
                  "boundary_people": len(outside_ids), "networks": network_counts}
        manifest = {
            "format_version": 1, "dataset_id": dataset_id, "selection": selection,
            "source": {"sha256": source_hashes, "coordinate_crs": "EPSG:4269"},
            "csv": {"null": "empty field", "geom": "original GeoPackage geometry bytes as hexadecimal"},
            "counts": counts,
            "quality": {"quarantined_rows": len(exceptions),
                        "missing_daytime_ids": sum(row["wp"] is None for row in people.values()),
                        "unresolved_workplace_ids": sum(row["site_type"] == "workplace" and
                            row["location_status"] != "available" for row in sites)},
            "files": files,
        }
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        if output_dir.exists():
            raise FileExistsError(output_dir)
        staging.rename(output_dir)
        return manifest
    except BaseException:
        shutil.rmtree(staging)
        raise
