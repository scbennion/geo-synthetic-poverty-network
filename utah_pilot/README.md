# Payson-area pilot

A small starting point for **Data Sources → Spatially-based properties → Network features → Synthetic Networks**. This exports existing synthetic people and ties, then loads them through the official Neo4j Python driver. Simulation, poverty outcomes and interventions are future work.

The initial selection uses four Utah County home tracts: `49049003401`, `49049003403`, `49049003404`, `49049003405`. Their synthetic home points cluster around Payson. This is a **Payson-area tract pilot**, with 15,507 residents; its extent follows the selected tracts rather than Payson’s legal city limits. It avoids starting with Provo or Orem, but no claim about school-size representativeness has been tested.

## Run locally

Use Python 3.12+ in a virtual environment. The original synthesis environment is separate.

```bash
python -m venv .venv-utah
source .venv-utah/bin/activate
python -m pip install -r requirements-utah-pilot.txt

# From the repository root. Keep data outside the Git checkout.
python -m utah_pilot extract \
  --input /path/to/unzipped/ut \
  --output /path/to/data/payson-area-pilot \
  --county 49049 \
  --tract 49049003401 --tract 49049003403 \
  --tract 49049003404 --tract 49049003405 \
  --area-name 'Payson-area four-tract pilot'

python -m utah_pilot plan /path/to/data/payson-area-pilot
python -m pytest tests -q
```

Extraction streams the state files, keeps complete households and preserves referenced destinations even outside the selected area. It normalizes and deduplicates undirected ties **within each network type**. It preserves people with no ties. It refuses an existing output directory and removes temporary output on failure. Both source and exported files receive SHA-256 checksums in `manifest.json`; source files are opened read-only.

For a later exact-city selection, `--boundary city.geojson` intersects the county/tract selection with a polygon in explicitly declared `EPSG:4269`. Selection includes points on the boundary. No external city boundary was used for this pilot. See [state formats](../docs/state-download-format.md) for the original download.

## Export files

| File | Contents |
|---|---|
| `population.csv` | All original columns for selected residents, including home and daytime IDs. |
| `households.csv` | `hhold`, `htype`, `member_count`, `long`, `lat`. |
| `sites.csv` | Referenced `wp`, type (`workplace`, `school`, `daycare`), available source coordinates/geometry and `location_status`. |
| `networks/{household,work,school,daycare}.csv` | Internal ties, each as `source,target`, one row per unordered pair per type. |
| `boundary_networks/{household,work,school,daycare}.csv` | Ties with exactly one selected resident. |
| `boundary_people.csv` | Original attributes of the directly connected outside residents; no recursive expansion. |
| `exceptions.csv` | Quarantined source rows with missing person IDs; details retain their original attributes. |
| `manifest.json` | Selection, source/output checksums, counts, coordinate system and quality findings. |

Empty CSV fields mean NULL. `geom` preserves the original GeoPackage geometry bytes as hexadecimal, **including its GeoPackage header**; it is not plain WKB. Shared IDs retain the original notation: person `id`, household `hhold`, daytime destination `wp`. `fid` is only a source-file row identifier. School/daycare assignments use `wp`, but their coordinates are absent from this state’s workplace file; they remain blank. No locations are invented. Source data with inconsistent households, invalid IDs or unknown edge endpoints fails explicitly.

The state population contains one row without a person ID. It is recorded in `exceptions.csv` even when outside the selected tracts; it is excluded from the graph. The extracted network is the original network restricted to selected residents, which removes some outside contacts. Use the boundary exports to measure that loss; they are excluded from the default Neo4j import to control size.

## Neo4j

Create an empty Aura Free instance or a local Neo4j database. `pip install neo4j` supplies the **Python driver**, while Aura or Desktop supplies the running database. Credentials come from environment variables; keep them out of the repository and shell scripts.

```bash
export NEO4J_URI='neo4j+s://your-instance.databases.neo4j.io'
export NEO4J_USERNAME='neo4j'
export NEO4J_DATABASE='neo4j'
read -s -p 'Neo4j password: ' NEO4J_PASSWORD; echo
export NEO4J_PASSWORD
python -m utah_pilot load /path/to/data/payson-area-pilot
unset NEO4J_PASSWORD
```

For a local server, set its `bolt://localhost:7687` URI. The loader validates the export before writing, checks the database’s existing size, then uses batched `UNWIND` / `MERGE` statements. Composite uniqueness constraints include `dataset_id`, so a rerun updates the same dataset without duplicating it. Batches commit separately: a failed import may be partial and can be resumed by rerunning the same immutable export.

| Nodes | Relationships |
|---|---|
| `PilotPerson` keyed by `dataset_id,id` | `LIVES_IN` → `PilotHousehold` |
| `PilotHousehold` keyed by `dataset_id,hhold` | `DAYTIME_AT` → `PilotSite` |
| `PilotSite` keyed by `dataset_id,wp` | `HOUSEHOLD_TIE`, `WORK_TIE`, `SCHOOL_TIE`, `DAYCARE_TIE` between residents |

Social relationships are stored once in canonical ID order; query them without arrow direction. Household/site membership edges have a different meaning from social ties. Home and workplace coordinates originate in NAD83 (`EPSG:4269`); the loader transforms available points to WGS84 for Neo4j while preserving the original coordinate attributes. Large source geometry blobs stay in the CSVs rather than consuming Aura space.

The capacity check includes **all nodes and membership/social relationships**, with current [Aura Free limits](https://neo4j.com/docs/aura/quotas-and-limits/) of 200,000 nodes and 400,000 relationships. Storage has a separate 1 GB limit; a count check does not guarantee available storage. Keep the pilot database dedicated to this import while loading it.

A local Neo4j 5.26.32 test loaded **27,622 nodes and 64,719 relationships**, reran without duplicates and executed all five exploration queries. There are 7,417 separate boundary ties to 6,817 outside people. Of the selected residents, 2,785 have no daytime ID; 59 referenced workplace IDs have no matching workplace record. Those locations remain unresolved.

To repeat the live integration test, set `UTAH_PILOT_LIVE_DIR` to the export directory alongside the `NEO4J_*` variables, then run `python -m pytest tests/test_utah_neo4j_live.py -q`. It loads the export twice and checks the queries. With those variables absent, the live test is skipped.

Open [explore.cypher](explore.cypher) in Neo4j Query / Browser for small visual neighborhoods, age bands, daytime sites and social degree. These queries use standard Cypher. Graph Data Science would be useful later for connected components and community detection **on social ties only**; it is optional and is not assumed to be installed or available on Aura Free. This pilot does not install it or compute those metrics.

## Scientific interpretation

- Home points and all people/ties are synthetic, not actual addresses or observed friendships. The [paper](https://doi.org/10.1038/s41597-024-03970-1) describes the synthetic population/network approach.
- [Network construction](../src/create_social_networks.py) uses undirected, unweighted graphs. Extraction retains supplied ties; it does not regenerate cliques or small-world networks for the smaller area.
- [Education assignment](../src/assign_education_site.py) stores school/daycare IDs in `wp`. A daytime assignment and a work-network edge are distinct relationships.
- [Person ID creation](../src/ctreate_individuals.py) encodes the home tract. That supports a reproducible tract selection without downloading another population dataset.
