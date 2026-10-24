"""Optional end-to-end check against a running Neo4j server; never deletes data."""

import json
import os
from pathlib import Path

import pytest


LIVE_VARIABLES = ("UTAH_PILOT_LIVE_DIR", "NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD")


@pytest.mark.skipif(not all(os.environ.get(name) for name in LIVE_VARIABLES),
                    reason="Set UTAH_PILOT_LIVE_DIR and NEO4J_* to run the live import test")
def test_live_import_rerun_and_exploration_queries():
    from neo4j import GraphDatabase
    from utah_pilot.neo4j_import import load_pilot, plan_import

    pilot = Path(os.environ["UTAH_PILOT_LIVE_DIR"])
    uri, username, password = (os.environ[name] for name in LIVE_VARIABLES[1:])
    database = os.environ.get("NEO4J_DATABASE", "neo4j")
    plan = plan_import(pilot)
    first = load_pilot(pilot, uri, username, password, database)
    second = load_pilot(pilot, uri, username, password, database)
    assert first == second
    assert second["verified"] is True
    parameters = {"dataset_id": plan["dataset_id"]}
    with GraphDatabase.driver(uri, auth=(username, password)) as driver:
        with driver.session(database=database) as session:
            record = session.run(
                "MATCH (p:PilotPerson {dataset_id:$dataset_id}) "
                "RETURN count(p) AS residents, count(p.location) AS located",
                **parameters,
            ).single()
            assert record["residents"] == plan["node_counts"]["PilotPerson"]
            assert record["located"] == record["residents"]
            parameters["person_id"] = session.run(
                "MATCH (p:PilotPerson {dataset_id:$dataset_id}) RETURN p.id AS id LIMIT 1",
                **parameters,
            ).single()["id"]
            query_file = Path(__file__).parents[1] / "utah_pilot" / "explore.cypher"
            statements = "\n".join(line for line in query_file.read_text().splitlines()
                                   if not line.lstrip().startswith("//"))
            for statement in statements.split(";"):
                if statement.strip():
                    assert session.run(statement, **parameters).data()
    report_path = os.environ.get("UTAH_PILOT_LIVE_REPORT")
    if report_path:
        Path(report_path).write_text(json.dumps({"first": first, "second": second,
                                                "idempotent": True,
                                                "exploration_queries_passed": 5}, indent=2) + "\n")
