"""Command line entry point; run from the repository root."""

import argparse
import json
import os
from pathlib import Path

from .extract import extract_county


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    extract = commands.add_parser("extract", help="Export existing residents and ties")
    extract.add_argument("--input", type=Path, required=True, help="Unzipped ut directory")
    extract.add_argument("--output", type=Path, required=True, help="New directory outside this repository")
    extract.add_argument("--county", default="49049")
    extract.add_argument("--tract", action="append", help="Repeat for explicit home-tract GEOIDs")
    extract.add_argument("--boundary", type=Path, help="Optional EPSG:4269 polygon GeoJSON")
    extract.add_argument("--area-name", default=None)
    plan = commands.add_parser("plan", help="Validate exports and show Neo4j capacity needed")
    plan.add_argument("pilot", type=Path)
    load = commands.add_parser("load", help="Import using NEO4J_* environment variables")
    load.add_argument("pilot", type=Path)
    load.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()
    if args.command == "extract":
        result = extract_county(args.input, args.output, args.county,
                               place_boundary=args.boundary, area_name=args.area_name,
                               home_tracts=args.tract)
    else:
        from .neo4j_import import load_pilot, plan_import
        if args.command == "plan":
            result = plan_import(args.pilot)
        else:
            required = ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD")
            missing = [name for name in required if not os.environ.get(name)]
            if missing:
                parser.error("Missing environment variables: " + ", ".join(missing))
            result = load_pilot(args.pilot, uri=os.environ["NEO4J_URI"],
                                username=os.environ["NEO4J_USERNAME"],
                                password=os.environ["NEO4J_PASSWORD"],
                                database=os.environ.get("NEO4J_DATABASE", "neo4j"),
                                batch_size=args.batch_size)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
