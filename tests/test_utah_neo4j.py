"""Check import validation, capacity accounting, and parameterized batch writes."""

import csv
import hashlib
import json
from copy import deepcopy

import pytest

from test_utah_extract import A, ISOLATE, OUTSIDE_CHILD, OUTSIDE_WORKER, SCHOOL, WORKPLACE, state_files
from utah_pilot.extract import extract_county
from utah_pilot import neo4j_import as importer


@pytest.fixture
def pilot(state_files, tmp_path):
    output = tmp_path / "pilot"
    extract_county(state_files, output)
    return output


def rewrite_csv(pilot, name, change):
    """Change a file and its manifest hash to exercise semantic validation."""
    path = pilot / name
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        header, rows = reader.fieldnames, list(reader)
    change(header, rows)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)
    manifest_path = pilot / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"][name] = {
        "rows": len(rows), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    manifest_path.write_text(json.dumps(manifest))


def empty_database(plan):
    return {
        "nodes": 0, "relationships": 0,
        "node_counts": dict.fromkeys(plan["node_counts"], 0),
        "relationship_counts": dict.fromkeys(plan["relationship_counts"], 0),
    }


def test_plan_counts_memberships_isolates_and_separate_tie_types(pilot):
    plan = importer.plan_import(pilot)
    assert plan["nodes"] == 13
    assert plan["relationships"] == 15
    assert plan["node_counts"] == {"PilotPerson": 6, "PilotHousehold": 4, "PilotSite": 3}
    assert plan["relationship_counts"] == {
        "LIVES_IN": 6, "DAYTIME_AT": 5, "HOUSEHOLD_TIE": 2,
        "WORK_TIE": 1, "SCHOOL_TIE": 1, "DAYCARE_TIE": 0,
    }
    assert plan["excluded_boundary_people"] == 2
    assert plan["excluded_boundary_relationships"] == 3


def test_modified_bytes_fail_checksum_before_connection(pilot, monkeypatch):
    import neo4j

    def no_connection(*args, **kwargs):
        pytest.fail("Validation must finish before opening a database connection")

    monkeypatch.setattr(neo4j.GraphDatabase, "driver", no_connection)
    with (pilot / "population.csv").open("a") as stream:
        stream.write("changed")
    with pytest.raises(ValueError, match="Checksum mismatch"):
        importer.load_pilot(pilot, "neo4j://unused", "user", "password")


def test_manifest_row_count_mismatch_is_rejected(pilot):
    path = pilot / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["files"]["population.csv"]["rows"] += 1
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Row count mismatch"):
        importer.plan_import(pilot)


@pytest.mark.parametrize("field,value,message", [
    ("hhold", "absent", "Unknown household reference"),
    ("wp", "absent", "Unknown daytime-site reference"),
    ("urban", "sometimes", "Invalid urban flag"),
    ("long", "NaN", "Non-finite"),
    ("lat", "", "Incomplete coordinates"),
])
def test_invalid_person_attributes_are_rejected(pilot, field, value, message):
    rewrite_csv(pilot, "population.csv", lambda header, rows: rows[0].update({field: value}))
    with pytest.raises(ValueError, match=message):
        importer.plan_import(pilot)


def test_duplicate_person_id_is_rejected(pilot):
    rewrite_csv(pilot, "population.csv", lambda header, rows: rows[1].update(id=rows[0]["id"]))
    with pytest.raises(ValueError, match="duplicate id"):
        importer.plan_import(pilot)


def test_internal_edges_cannot_reference_external_people(pilot):
    rewrite_csv(pilot, "networks/work.csv", lambda header, rows: rows[0].update(source=OUTSIDE_WORKER))
    with pytest.raises(ValueError, match="Unknown internal endpoint"):
        importer.plan_import(pilot)


def test_reciprocal_or_duplicate_exported_edges_are_rejected(pilot):
    rewrite_csv(pilot, "networks/work.csv", lambda header, rows: rows.append(dict(rows[0])))
    with pytest.raises(ValueError, match="duplicate edge"):
        importer.plan_import(pilot)


def test_empty_network_still_requires_source_target_header(pilot):
    rewrite_csv(pilot, "networks/daycare.csv", lambda header, rows: header.__setitem__(0, "wrong"))
    with pytest.raises(ValueError, match="Unexpected CSV columns"):
        importer.plan_import(pilot)


def test_invalid_site_numeric_attribute_is_rejected_during_planning(pilot):
    rewrite_csv(pilot, "sites.csv", lambda header, rows: rows[0].update(fid="invalid"))
    with pytest.raises(ValueError, match="Invalid fid"):
        importer.plan_import(pilot)


def test_boundary_people_must_resolve_all_external_endpoints(pilot):
    rewrite_csv(pilot, "boundary_people.csv", lambda header, rows: rows.pop())
    with pytest.raises(ValueError, match="Invalid boundary endpoints"):
        importer.plan_import(pilot)


def test_capacity_includes_existing_database_and_allows_exact_limit(pilot):
    plan = importer.plan_import(pilot)
    existing = empty_database(plan)
    existing["nodes"] = importer.MAX_NODES - plan["nodes"]
    existing["relationships"] = importer.MAX_RELATIONSHIPS - plan["relationships"]
    assert importer._check_capacity(plan, existing) == {
        "nodes": importer.MAX_NODES, "relationships": importer.MAX_RELATIONSHIPS,
    }
    existing["relationships"] += 1
    with pytest.raises(ValueError, match="capacity exceeded"):
        importer._check_capacity(plan, existing)


def test_capacity_subtracts_existing_same_dataset_for_idempotent_rerun(pilot):
    plan = importer.plan_import(pilot)
    existing = {
        "nodes": importer.MAX_NODES, "relationships": importer.MAX_RELATIONSHIPS,
        "node_counts": plan["node_counts"], "relationship_counts": plan["relationship_counts"],
    }
    assert importer._check_capacity(plan, existing) == {
        "nodes": importer.MAX_NODES, "relationships": importer.MAX_RELATIONSHIPS,
    }


class FakeResult:
    def consume(self):
        return None


class FakeSession:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def run(self, query, **parameters):
        self.calls.append((query, deepcopy(parameters)))
        return FakeResult()

    def execute_write(self, function, *args):
        return function(self, *args)


class FakeDriver:
    def __init__(self, session):
        self.fake_session = session

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def verify_connectivity(self):
        pass

    def session(self, **kwargs):
        assert kwargs == {"database": "neo4j"}
        return self.fake_session


def fake_import_connection(monkeypatch, plan, before=None, after=None):
    import neo4j

    session = FakeSession()
    monkeypatch.setattr(neo4j.GraphDatabase, "driver", lambda *args, **kwargs: FakeDriver(session))
    responses = iter([
        before if before is not None else empty_database(plan),
        after if after is not None else {
            "nodes": plan["nodes"], "relationships": plan["relationships"],
            "node_counts": plan["node_counts"], "relationship_counts": plan["relationship_counts"],
        },
    ])
    monkeypatch.setattr(importer, "_database_counts", lambda *args: next(responses))
    return session


def test_import_batches_namespaced_merges_preserves_nulls_and_excludes_boundary(pilot, monkeypatch):
    plan = importer.plan_import(pilot)
    session = fake_import_connection(monkeypatch, plan)
    report = importer.load_pilot(pilot, "neo4j://unused", "user", "password", batch_size=2)
    assert report["verified"] is True
    assert report["geometry_bytes_imported"] is False
    batches = [(query, parameters) for query, parameters in session.calls if "UNWIND" in query]
    assert all(len(parameters["rows"]) <= 2 for _, parameters in batches)
    assert all(parameters["dataset_id"] == plan["dataset_id"] for _, parameters in batches)
    assert all("MERGE" in query for query, _ in batches)
    assert all("DELETE" not in query for query, _ in session.calls)
    person_rows = {
        row["key"]: row for query, parameters in batches if "MERGE (n:PilotPerson " in query
        for row in parameters["rows"]
    }
    assert len(person_rows) == 6
    assert OUTSIDE_WORKER not in person_rows and OUTSIDE_CHILD not in person_rows
    assert person_rows[ISOLATE]["props"]["wp"] is None
    assert person_rows[A]["props"]["age"] == 30
    assert person_rows[A]["props"]["urban"] is True
    assert person_rows[A]["props"]["wp"] == WORKPLACE
    assert "geom" not in person_rows[A]["props"]
    point = person_rows[A]["location"]
    assert point["crs"] == "wgs-84"
    assert point["longitude"] == pytest.approx(-111.6, abs=0.001)
    assert point["latitude"] == pytest.approx(40.2, abs=0.001)
    site_rows = {
        row["key"]: row for query, parameters in batches if "MERGE (n:PilotSite " in query
        for row in parameters["rows"]
    }
    assert site_rows[SCHOOL]["location"] is None
    assert site_rows[WORKPLACE]["location"]["longitude"] == pytest.approx(-112, abs=0.001)
    for relationship in ("HOUSEHOLD_TIE", "WORK_TIE", "SCHOOL_TIE"):
        assert any(f"r:{relationship} " in query for query, _ in batches)


def test_capacity_failure_happens_before_constraint_or_data_writes(pilot, monkeypatch):
    plan = importer.plan_import(pilot)
    existing = empty_database(plan)
    existing["nodes"] = importer.MAX_NODES
    session = fake_import_connection(monkeypatch, plan, before=existing)
    with pytest.raises(ValueError, match="capacity exceeded"):
        importer.load_pilot(pilot, "neo4j://unused", "user", "password")
    assert session.calls == []


def test_post_import_count_mismatch_fails_explicitly(pilot, monkeypatch):
    plan = importer.plan_import(pilot)
    fake_import_connection(monkeypatch, plan, after=empty_database(plan))
    with pytest.raises(RuntimeError, match="Post-import graph counts"):
        importer.load_pilot(pilot, "neo4j://unused", "user", "password")


@pytest.mark.parametrize("batch_size", [0, -1, 1.5, True])
def test_invalid_batch_size_is_rejected(pilot, batch_size):
    with pytest.raises(ValueError, match="positive integer"):
        importer.load_pilot(pilot, "neo4j://unused", "user", "password", batch_size=batch_size)
