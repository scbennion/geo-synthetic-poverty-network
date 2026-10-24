"""Behavioral checks for county extraction, from parsers to complete exports."""

import csv
import hashlib
import sqlite3
from pathlib import Path

import pytest

from utah_pilot.extract import (
    canonical_edge,
    extract_county,
    iter_network,
    parse_person_id,
)


A = "49049000100i0"
B = "49049000100i1"
ISOLATE = "49049000100i2"
CHILD_A = "49049000200i0"
CHILD_B = "49049000200i1"
DAYCARE_CHILD = "49049000300i0"
OUTSIDE_WORKER = "49035000100i0"
OUTSIDE_CHILD = "49035000200i0"
UNRELATED_OUTSIDE_PERSON = "49035000400i0"
WORKPLACE = "49035000100w0"
SCHOOL = "49035000200s0"
DAYCARE = "49035000300d0"

POPULATION_COLUMNS = (
    "fid", "geom", "id", "age", "gender", "assigned", "hhold", "htype",
    "wp", "urban", "long", "lat",
)


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        csv.writer(stream).writerows(rows)


def read_csv(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def read_pairs(path):
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == ["source", "target"]
        pairs = [(row["source"], row["target"]) for row in reader]
    assert len(pairs) == len(set(pairs)), "Export contains duplicate edges"
    assert all(source < target for source, target in pairs)
    return set(pairs)


def person(fid, person_id, household, daytime, age=30, long=-111.6, lat=40.2):
    return (
        fid, b"\x01\x02", person_id, age, "f", 1, household, 1,
        daytime, 1, long, lat,
    )


@pytest.fixture
def state_files(tmp_path):
    """Create only the source attributes needed by the public extractor contract."""
    root = tmp_path / "ut"
    root.mkdir()
    population = sqlite3.connect(root / "ut_population.gpkg")
    population.execute(
        "CREATE TABLE ut_population ("
        "fid INTEGER PRIMARY KEY, geom BLOB, id TEXT, age REAL, gender TEXT, "
        "assigned REAL, hhold TEXT, htype REAL, wp TEXT, urban INTEGER, "
        "long REAL, lat REAL)"
    )
    rows = [
        person(1, A, "49049000100h0", WORKPLACE),
        person(2, B, "49049000100h0", WORKPLACE),
        person(3, ISOLATE, "49049000100h1", None),
        person(4, CHILD_A, "49049000200h0", SCHOOL, age=10),
        person(5, CHILD_B, "49049000200h0", SCHOOL, age=12),
        person(6, DAYCARE_CHILD, "49049000300h0", DAYCARE, age=3),
        person(7, OUTSIDE_WORKER, "49035000100h0", WORKPLACE),
        person(8, OUTSIDE_CHILD, "49035000200h0", SCHOOL, age=10),
        person(9, UNRELATED_OUTSIDE_PERSON, "49035000400h0", None),
        (10, b"\x00", None, None, None, None, "49051000100h9", 10,
         None, 1, -111.4, 40.4),
    ]
    population.executemany(
        "INSERT INTO ut_population VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    population.commit()
    population.close()

    workplaces = sqlite3.connect(root / "ut_workplace.gpkg")
    workplaces.execute(
        "CREATE TABLE ut_workplace (fid INTEGER PRIMARY KEY, geom BLOB, "
        "wp TEXT, long REAL, lat REAL)"
    )
    workplaces.executemany(
        "INSERT INTO ut_workplace VALUES (?, ?, ?, ?, ?)",
        [
            (1, b"\x03\x04", WORKPLACE, -112.0, 40.5),
            (2, b"\x05\x06", "49049000900w99", -111.0, 40.0),
        ],
    )
    workplaces.commit()
    workplaces.close()

    networks = root / "social_networks"
    write_csv(networks / "ut_household_network.csv", [
        [A, B], [B, A], [ISOLATE], [CHILD_A, CHILD_B], [CHILD_B, CHILD_A],
        [DAYCARE_CHILD], [OUTSIDE_WORKER], [OUTSIDE_CHILD],
        [UNRELATED_OUTSIDE_PERSON],
    ])
    write_csv(networks / "ut_school_network.csv", [
        [CHILD_A, CHILD_B, OUTSIDE_CHILD], [CHILD_B, CHILD_A],
        [OUTSIDE_CHILD, CHILD_A],
    ])
    write_csv(networks / "ut_daycare_network.csv", [[DAYCARE_CHILD]])
    write_csv(networks / "ut_work_network.csv", [
        ["", "source", "target"],
        [100, OUTSIDE_WORKER, A],
        [101, B, OUTSIDE_WORKER],
        [102, B, A],
        [103, A, B],
    ])
    return root


@pytest.mark.parametrize("person_id,county", [(A, "49049"), (OUTSIDE_CHILD, "49035")])
def test_person_id_returns_encoded_home_county(person_id, county):
    assert parse_person_id(person_id) == county


@pytest.mark.parametrize("person_id", [
    "", "4904900010i0", "490490001000i0", "49049000100w0",
    "49049000100i", "49049000100i-1", "49049000100i1junk",
])
def test_invalid_person_id_raises(person_id):
    with pytest.raises(ValueError):
        parse_person_id(person_id)


def test_canonical_edge_ignores_endpoint_order():
    assert canonical_edge(A, B) == (A, B)
    assert canonical_edge(B, A) == (A, B)


def test_self_edge_raises():
    with pytest.raises(ValueError):
        canonical_edge(A, A)


@pytest.mark.parametrize("network_type", ["household", "school", "daycare"])
def test_adjacency_parser_keeps_each_neighbor_and_accepts_isolate(tmp_path, network_type):
    path = tmp_path / "network.csv"
    write_csv(path, [[A, B, CHILD_A], [ISOLATE]])
    assert list(iter_network(path, network_type)) == [(A, B), (A, CHILD_A)]


def test_work_parser_ignores_numeric_export_index(tmp_path):
    path = tmp_path / "work.csv"
    write_csv(path, [["", "source", "target"], [191350260, A, B]])
    assert list(iter_network(path, "work")) == [(A, B)]


@pytest.mark.parametrize("header", [
    ["source", "target"], ["index", "source", "target"],
    ["", "target", "source"],
])
def test_work_parser_rejects_unexpected_header(tmp_path, header):
    path = tmp_path / "work.csv"
    write_csv(path, [header, [100, A, B]])
    with pytest.raises(ValueError):
        list(iter_network(path, "work"))


def test_extract_preserves_residents_households_sites_and_boundary_context(state_files, tmp_path):
    output = tmp_path / "pilot"
    source_hashes = {
        path.relative_to(state_files): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in state_files.rglob("*") if path.is_file()
    }
    manifest = extract_county(state_files, output)
    assert isinstance(manifest, dict)

    people = {row["id"]: row for row in read_csv(output / "population.csv")}
    assert set(people) == {A, B, ISOLATE, CHILD_A, CHILD_B, DAYCARE_CHILD}
    assert set(POPULATION_COLUMNS) <= people[A].keys()
    assert people[A]["geom"].lower() == "0102"
    assert float(people[A]["age"]) == 30
    assert people[A]["gender"] == "f"
    assert people[A]["hhold"] == "49049000100h0"
    assert people[ISOLATE]["wp"] == ""

    households = {row["hhold"]: row for row in read_csv(output / "households.csv")}
    assert len(households) == 4
    assert int(households["49049000100h0"]["member_count"]) == 2
    assert int(households["49049000100h1"]["member_count"]) == 1

    sites = {row["wp"]: row for row in read_csv(output / "sites.csv")}
    assert set(sites) == {WORKPLACE, SCHOOL, DAYCARE}
    assert sites[WORKPLACE]["site_type"] == "workplace"
    assert float(sites[WORKPLACE]["long"]) == -112.0
    assert float(sites[WORKPLACE]["lat"]) == 40.5
    for site, kind in [(SCHOOL, "school"), (DAYCARE, "daycare")]:
        assert sites[site]["site_type"] == kind
        assert sites[site]["long"] == sites[site]["lat"] == ""
        assert sites[site]["location_status"]

    internal = output / "networks"
    assert read_pairs(internal / "household.csv") == {(A, B), (CHILD_A, CHILD_B)}
    assert read_pairs(internal / "school.csv") == {(CHILD_A, CHILD_B)}
    assert read_pairs(internal / "work.csv") == {(A, B)}
    assert read_pairs(internal / "daycare.csv") == set()

    boundary = output / "boundary_networks"
    assert read_pairs(boundary / "work.csv") == {
        canonical_edge(A, OUTSIDE_WORKER), canonical_edge(B, OUTSIDE_WORKER),
    }
    assert read_pairs(boundary / "school.csv") == {canonical_edge(CHILD_A, OUTSIDE_CHILD)}
    assert read_pairs(boundary / "household.csv") == set()
    assert read_pairs(boundary / "daycare.csv") == set()
    external_people = {row["id"]: row for row in read_csv(output / "boundary_people.csv")}
    assert set(external_people) == {OUTSIDE_WORKER, OUTSIDE_CHILD}
    assert external_people[OUTSIDE_CHILD]["wp"] == SCHOOL

    exceptions = read_csv(output / "exceptions.csv")
    assert exceptions
    assert all({"source", "record", "kind", "detail"} <= row.keys() for row in exceptions)
    assert any("id" in row["kind"].lower() for row in exceptions)
    assert source_hashes == {
        path.relative_to(state_files): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in state_files.rglob("*") if path.is_file()
    }


def test_existing_output_is_preserved(state_files, tmp_path):
    output = tmp_path / "pilot"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("Existing output must survive.")
    with pytest.raises(FileExistsError):
        extract_county(state_files, output)
    assert sentinel.read_text() == "Existing output must survive."
    assert sorted(path.name for path in output.iterdir()) == ["keep.txt"]


def test_unknown_network_endpoint_fails_without_partial_output(state_files, tmp_path):
    write_csv(state_files / "social_networks/ut_work_network.csv", [
        ["", "source", "target"], [100, A, "49035009999i999"],
    ])
    output = tmp_path / "pilot"
    with pytest.raises(ValueError):
        extract_county(state_files, output)
    assert not output.exists()


def test_invalid_header_fails_without_partial_output(state_files, tmp_path):
    write_csv(state_files / "social_networks/ut_work_network.csv", [
        ["wrong", "source", "target"], [100, A, B],
    ])
    output = tmp_path / "pilot"
    with pytest.raises(ValueError):
        extract_county(state_files, output)
    assert not output.exists()


def test_explicit_home_tract_selection_keeps_complete_households(state_files, tmp_path):
    output = tmp_path / "tracts"
    result = extract_county(state_files, output, home_tracts=["49049000100"])
    assert result["counts"]["population"] == 3
    assert {r["id"] for r in read_csv(output / "population.csv")} == {A, B, ISOLATE}
    assert result["selection"]["home_tracts"] == ["49049000100"]


@pytest.mark.parametrize("tracts", [[], ["49035000100"], ["4904900010"], ["49049000100i"]])
def test_bad_tract_selection_is_rejected(state_files, tmp_path, tracts):
    with pytest.raises(ValueError, match="Home tracts"):
        extract_county(state_files, tmp_path / "bad", home_tracts=tracts)


def test_boundary_uses_home_point_and_includes_polygon_edge(state_files, tmp_path):
    import json
    boundary = tmp_path / "boundary.geojson"
    boundary.write_text(json.dumps({
        "type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": "EPSG:4269"}},
        "features": [{"type": "Feature", "properties": {}, "geometry": {
            "type": "Polygon", "coordinates": [[[-111.6, 40], [-111, 40], [-111, 41],
                                                    [-111.6, 41], [-111.6, 40]]]}}],
    }))
    result = extract_county(state_files, tmp_path / "bounded", place_boundary=boundary)
    assert result["counts"]["population"] == 6
    assert (tmp_path / "bounded" / "boundary.geojson").exists()


def test_boundary_with_ambiguous_crs_fails(state_files, tmp_path):
    import json
    boundary = tmp_path / "boundary.geojson"
    boundary.write_text(json.dumps({"type": "FeatureCollection", "features": []}))
    with pytest.raises(ValueError, match="EPSG:4269"):
        extract_county(state_files, tmp_path / "bad", place_boundary=boundary)


def test_duplicate_workplace_with_missing_coordinates_is_not_overwritten(state_files, tmp_path):
    with sqlite3.connect(state_files / "ut_workplace.gpkg") as db:
        db.execute("UPDATE ut_workplace SET long=NULL, lat=NULL WHERE wp=?", (WORKPLACE,))
        db.execute("INSERT INTO ut_workplace VALUES (3, NULL, ?, -112, 40.5)", (WORKPLACE,))
    output = tmp_path / "duplicate"
    with pytest.raises(ValueError, match="Duplicate workplace"):
        extract_county(state_files, output)
    assert not output.exists()
