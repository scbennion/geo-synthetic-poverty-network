"""Validate and import an extracted pilot into an existing Neo4j database.

Only selected residents and internal ties are imported. Boundary context stays
in the pilot files. Original geometry bytes remain in CSV; Neo4j receives the
attributes and a WGS84 point transformed from the original NAD83 coordinates.
"""

import csv
import hashlib
import io
import json
import math
from collections import Counter
from pathlib import Path


MAX_NODES = 200_000
MAX_RELATIONSHIPS = 400_000
NETWORK_RELATIONSHIPS = {
    "household": "HOUSEHOLD_TIE",
    "work": "WORK_TIE",
    "school": "SCHOOL_TIE",
    "daycare": "DAYCARE_TIE",
}
NODE_LABELS = ("PilotPerson", "PilotHousehold", "PilotSite")
RELATIONSHIP_TYPES = ("LIVES_IN", "DAYTIME_AT", *NETWORK_RELATIONSHIPS.values())
CSV_COLUMNS = {
    "population.csv": {"fid", "geom", "id", "age", "gender", "assigned", "hhold", "htype",
                       "wp", "urban", "long", "lat"},
    "households.csv": {"hhold", "htype", "member_count", "long", "lat"},
    "sites.csv": {"wp", "site_type", "long", "lat", "geom", "fid", "location_status"},
    "exceptions.csv": {"source", "record", "kind", "detail"},
}
CSV_COLUMNS["boundary_people.csv"] = CSV_COLUMNS["population.csv"]


def _unique(rows, key, name):
    result = {}
    for row in rows:
        value = row.get(key)
        if not value or value in result:
            raise ValueError(f"Missing or duplicate {key} in {name}: {value!r}")
        result[value] = row
    return result


def _number(value, field):
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid {field}: {value!r}") from error
    if not math.isfinite(number):
        raise ValueError(f"Non-finite {field}: {value!r}")
    return number


def _check_coordinates(row, name):
    longitude = _number(row.get("long"), "longitude")
    latitude = _number(row.get("lat"), "latitude")
    if (longitude is None) != (latitude is None):
        raise ValueError(f"Incomplete coordinates in {name}")
    if longitude is not None and not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
        raise ValueError(f"Coordinates outside geographic bounds in {name}")


def _read_files(root, manifest):
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError("Manifest must contain a files mapping")
    result = {}
    for name, metadata in files.items():
        path = (root / name).resolve()
        if Path(name).is_absolute() or not path.is_relative_to(root):
            raise ValueError(f"File path escapes pilot directory: {name}")
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != metadata.get("sha256"):
            raise ValueError(f"Checksum mismatch: {name}")
        if "rows" not in metadata:
            continue
        reader = csv.DictReader(io.StringIO(content.decode("utf-8"), newline=""))
        header = reader.fieldnames
        if not header or len(header) != len(set(header)):
            raise ValueError(f"Missing or duplicate CSV header: {name}")
        expected = CSV_COLUMNS.get(name)
        if name.startswith(("networks/", "boundary_networks/")):
            expected = {"source", "target"}
        if expected is not None and set(header) != expected:
            raise ValueError(f"Unexpected CSV columns: {name}")
        rows = list(reader)
        if any(None in row or any(value is None for value in row.values()) for row in rows):
            raise ValueError(f"Malformed CSV row: {name}")
        if len(rows) != metadata["rows"]:
            raise ValueError(f"Row count mismatch: {name}")
        result[name] = rows
    return result


def _validated_data(pilot_dir):
    root = Path(pilot_dir).resolve()
    manifest = json.loads((root / "manifest.json").read_text())
    if manifest.get("format_version") != 1 or not manifest.get("dataset_id"):
        raise ValueError("Unsupported manifest or missing dataset_id")
    if manifest.get("source", {}).get("coordinate_crs") != "EPSG:4269":
        raise ValueError("Expected source coordinates labeled EPSG:4269")
    data = _read_files(root, manifest)
    required = {"population.csv", "households.csv", "sites.csv", "boundary_people.csv", "exceptions.csv"}
    required.update(f"{directory}/{kind}.csv" for directory in ("networks", "boundary_networks")
                    for kind in NETWORK_RELATIONSHIPS)
    if not required <= data.keys():
        raise ValueError(f"Missing pilot CSVs: {sorted(required - data.keys())}")

    people = _unique(data["population.csv"], "id", "population.csv")
    households = _unique(data["households.csv"], "hhold", "households.csv")
    sites = _unique(data["sites.csv"], "wp", "sites.csv")
    external = _unique(data["boundary_people.csv"], "id", "boundary_people.csv")
    if people.keys() & external.keys():
        raise ValueError("Boundary people overlap selected residents")
    all_people = people.keys() | external.keys()
    members = Counter()
    daytime = 0
    for person in people.values():
        household = person.get("hhold")
        if household not in households:
            raise ValueError(f"Unknown household reference: {household!r}")
        members[household] += 1
        if person.get("wp"):
            if person["wp"] not in sites:
                raise ValueError(f"Unknown daytime-site reference: {person['wp']}")
            daytime += 1
        for field in ("age", "assigned", "htype", "fid"):
            _number(person.get(field), field)
        if person.get("urban") not in ("", "0", "1", "True", "False", "true", "false"):
            raise ValueError(f"Invalid urban flag: {person.get('urban')!r}")
        _check_coordinates(person, person["id"])
    for household in households.values():
        count = _number(household.get("member_count"), "member_count")
        if count != members[household["hhold"]]:
            raise ValueError(f"Household member count mismatch: {household['hhold']}")
        _number(household.get("htype"), "htype")
        _check_coordinates(household, household["hhold"])
    site_types = Counter()
    for site in sites.values():
        if site.get("site_type") not in ("workplace", "school", "daycare"):
            raise ValueError(f"Unknown site type: {site.get('site_type')!r}")
        site_types[site["site_type"]] += 1
        _number(site.get("fid"), "fid")
        _check_coordinates(site, site["wp"])

    relationship_counts = {"LIVES_IN": len(people), "DAYTIME_AT": daytime}
    boundary_total = 0
    for kind, relationship_type in NETWORK_RELATIONSHIPS.items():
        for directory in ("networks", "boundary_networks"):
            edges = data[f"{directory}/{kind}.csv"]
            seen = set()
            for edge in edges:
                if set(edge) != {"source", "target"}:
                    raise ValueError(f"Unexpected edge columns: {directory}/{kind}.csv")
                source, target = edge["source"], edge["target"]
                if source >= target or (source, target) in seen:
                    raise ValueError(f"Noncanonical or duplicate edge: {source}, {target}")
                seen.add((source, target))
                selected = int(source in people) + int(target in people)
                if directory == "networks" and selected != 2:
                    raise ValueError(f"Unknown internal endpoint: {source}, {target}")
                if directory == "boundary_networks" and (
                    selected != 1 or source not in all_people or target not in all_people
                ):
                    raise ValueError(f"Invalid boundary endpoints: {source}, {target}")
            count_key = "internal" if directory == "networks" else "boundary"
            if len(edges) != manifest["counts"]["networks"][kind][count_key]:
                raise ValueError(f"Manifest network count mismatch: {kind}/{count_key}")
            if directory == "networks":
                relationship_counts[relationship_type] = len(edges)
            else:
                boundary_total += len(edges)
    counts = manifest["counts"]
    if (counts["population"] != len(people) or counts["households"] != len(households)
            or counts["sites"] != dict(site_types) or counts["boundary_people"] != len(external)):
        raise ValueError("Manifest node counts do not match CSV contents")
    node_counts = {"PilotPerson": len(people), "PilotHousehold": len(households), "PilotSite": len(sites)}
    plan = {
        "dataset_id": manifest["dataset_id"],
        "nodes": sum(node_counts.values()),
        "relationships": sum(relationship_counts.values()),
        "node_counts": node_counts,
        "relationship_counts": relationship_counts,
        "excluded_boundary_people": len(external),
        "excluded_boundary_relationships": boundary_total,
    }
    return data, plan


def plan_import(pilot_dir):
    """Validate all exported files and return exact selected-area graph counts."""
    _, plan = _validated_data(pilot_dir)
    return plan


def _count(session, query, **parameters):
    return session.run(query, **parameters).single()["count"]


def _database_counts(session, dataset_id):
    total_nodes = _count(session, "MATCH (n) RETURN count(n) AS count")
    total_relationships = _count(session, "MATCH ()-[r]->() RETURN count(r) AS count")
    if total_nodes == 0:
        return {"nodes": 0, "relationships": total_relationships,
                "node_counts": dict.fromkeys(NODE_LABELS, 0),
                "relationship_counts": dict.fromkeys(RELATIONSHIP_TYPES, 0)}
    node_counts = {
        label: _count(session, f"MATCH (n:{label} {{dataset_id: $dataset_id}}) RETURN count(n) AS count",
                      dataset_id=dataset_id)
        for label in NODE_LABELS
    }
    relationship_counts = {
        kind: _count(session, f"MATCH (a:PilotPerson)-[r:{kind}]->(b) "
                     "WHERE r.dataset_id = $dataset_id AND a.dataset_id = $dataset_id "
                     "AND b.dataset_id = $dataset_id "
                     "AND (b:PilotPerson OR b:PilotHousehold OR b:PilotSite) "
                     "RETURN count(r) AS count", dataset_id=dataset_id)
        for kind in RELATIONSHIP_TYPES
    }
    return {
        "nodes": total_nodes,
        "relationships": total_relationships,
        "node_counts": node_counts,
        "relationship_counts": relationship_counts,
    }


def _check_capacity(plan, existing):
    for key in ("node_counts", "relationship_counts"):
        if any(existing[key][kind] > count for kind, count in plan[key].items()):
            raise ValueError("Existing dataset contains more entities than this pilot; refusing to alter it")
    projected = {
        "nodes": existing["nodes"] - sum(existing["node_counts"].values()) + plan["nodes"],
        "relationships": existing["relationships"] - sum(existing["relationship_counts"].values())
                         + plan["relationships"],
    }
    if projected["nodes"] > MAX_NODES or projected["relationships"] > MAX_RELATIONSHIPS:
        raise ValueError(f"Aura Free capacity exceeded: {projected['nodes']} nodes, "
                         f"{projected['relationships']} relationships")
    return projected


def _properties(row, transformer):
    properties = {key: value or None for key, value in row.items()
                  if key not in ("id", "hhold", "wp", "dataset_id", "geom")}
    for key in ("age", "assigned", "htype", "fid", "member_count", "long", "lat"):
        if key in properties:
            properties[key] = _number(properties[key], key)
    if "urban" in properties:
        value = properties["urban"]
        properties["urban"] = None if value is None else value.lower() in ("1", "true")
    # Retain assignment identifiers as attributes as well as graph relationships.
    for key in ("hhold", "wp"):
        if key in row:
            properties[key] = row[key] or None
    location = None
    if properties.get("long") is not None:
        longitude, latitude = transformer.transform(properties["long"], properties["lat"], errcheck=True)
        location = {"longitude": longitude, "latitude": latitude, "crs": "wgs-84"}
    properties["source_crs"] = "EPSG:4269"
    return properties, location


def _write_batch(transaction, query, dataset_id, rows):
    transaction.run(query, dataset_id=dataset_id, rows=rows).consume()


def _write(session, query, dataset_id, rows, batch_size):
    batch = []
    for row in rows:
        batch.append(row)
        if len(batch) == batch_size:
            session.execute_write(_write_batch, query, dataset_id, batch)
            batch = []
    if batch:
        session.execute_write(_write_batch, query, dataset_id, batch)


def load_pilot(pilot_dir, uri, username, password, database="neo4j", batch_size=1000):
    """MERGE a validated pilot without deleting existing database content.

    Capacity includes all database content and excludes already loaded entities
    of this dataset when estimating additions, so rerunning is idempotent.
    """
    from neo4j import GraphDatabase
    from pyproj import Transformer

    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
        raise ValueError("batch_size must be a positive integer")
    data, plan = _validated_data(pilot_dir)
    if plan["nodes"] > MAX_NODES or plan["relationships"] > MAX_RELATIONSHIPS:
        raise ValueError("Pilot alone exceeds Aura Free capacity")
    transformer = Transformer.from_crs("EPSG:4269", "EPSG:4326", always_xy=True)
    dataset_id = plan["dataset_id"]
    with GraphDatabase.driver(uri, auth=(username, password)) as driver:
        driver.verify_connectivity()
        with driver.session(database=database) as session:
            projected = _check_capacity(plan, _database_counts(session, dataset_id))
            for label, key in (("PilotPerson", "id"), ("PilotHousehold", "hhold"), ("PilotSite", "wp")):
                session.run(f"CREATE CONSTRAINT {label.lower()}_identity IF NOT EXISTS "
                            f"FOR (n:{label}) REQUIRE (n.dataset_id, n.{key}) IS UNIQUE").consume()
            for filename, label, key in (("population.csv", "PilotPerson", "id"),
                                         ("households.csv", "PilotHousehold", "hhold"),
                                         ("sites.csv", "PilotSite", "wp")):
                def node_rows():
                    for row in data[filename]:
                        properties, location = _properties(row, transformer)
                        yield {"key": row[key], "props": properties, "location": location}

                query = (f"UNWIND $rows AS row MERGE (n:{label} "
                         f"{{dataset_id: $dataset_id, {key}: row.key}}) SET n += row.props "
                         "SET n.location = CASE WHEN row.location IS NULL THEN null "
                         "ELSE point(row.location) END")
                _write(session, query, dataset_id, node_rows(), batch_size)
            for relationship, label, key in (("LIVES_IN", "PilotHousehold", "hhold"),
                                              ("DAYTIME_AT", "PilotSite", "wp")):
                rows = ({"source": row["id"], "target": row[key]}
                        for row in data["population.csv"] if row.get(key))
                query = ("UNWIND $rows AS row MATCH (a:PilotPerson "
                         "{dataset_id: $dataset_id, id: row.source}) "
                         f"MATCH (b:{label} {{dataset_id: $dataset_id, {key}: row.target}}) "
                         f"MERGE (a)-[r:{relationship} {{dataset_id: $dataset_id}}]->(b)")
                _write(session, query, dataset_id, rows, batch_size)
            for kind, relationship in NETWORK_RELATIONSHIPS.items():
                query = ("UNWIND $rows AS row MATCH (a:PilotPerson "
                         "{dataset_id: $dataset_id, id: row.source}) "
                         "MATCH (b:PilotPerson {dataset_id: $dataset_id, id: row.target}) "
                         f"MERGE (a)-[r:{relationship} {{dataset_id: $dataset_id}}]->(b)")
                _write(session, query, dataset_id, data[f"networks/{kind}.csv"], batch_size)
            actual = _database_counts(session, dataset_id)
            if any(actual[key] != plan[key] for key in ("node_counts", "relationship_counts")):
                raise RuntimeError("Post-import graph counts differ from the validated plan")
    return {**plan, "database": database, "projected_database_counts": projected,
            "verified": True, "geometry_bytes_imported": False}
