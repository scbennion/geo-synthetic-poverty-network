# Validation and download inventory

Prepared October 23, 2026 (America/Denver). Branch: `pilot/payson-neo4j`. Source data and exports are outside the repository. No commits or pushes have been made for this pilot.

## Result

The **Payson-area four-tract pilot** selects home tracts `49049003401`, `49049003403`, `49049003404`, `49049003405` within Utah County (`49049`). It is a reproducible small geographic pilot; its boundary is not Payson's legal city limits. All residents in those source tracts are retained, including isolates. Referenced destinations can be outside the pilot.

| Item | Count |
|---|---:|
| Residents | 15,507 |
| Households | 4,514 |
| Referenced workplaces | 7,588 |
| Referenced schools / daycares | 11 / 2 |
| Outside people retained separately | 6,817 |
| Neo4j nodes, including households and sites | 27,622 |
| Neo4j relationships, including membership | 64,719 |

| Social network | Internal ties | Boundary ties |
|---|---:|---:|
| Household | 25,015 | 0 |
| Work | 106 | 3,936 |
| School | 8,564 | 2,067 |
| Daycare | 2,805 | 1,414 |

Boundary ties remain in the export and are excluded from the default import. Most work ties cross this pilot's boundary, so internal work-network statistics describe a restricted subset. These files do not establish that local schools are representative or that referenced workplace IDs are observed businesses.

Quality findings: 2,785 selected residents have NULL daytime assignments. There are 59 workplace references without matching source workplace records; their location fields remain NULL. All 13 school/daycare site locations are unavailable in the workplace file. One state population row has no person ID; its original attributes are retained in the exceptions file and it is excluded from the graph.

## Checks performed

- 53 unit/fixture tests pass. They cover CSV formats, tract selection, boundary CRS/edge inclusion, IDs, isolates, households, sites, typed deduplication, boundary context, atomic failure, source preservation, checksums, foreign keys, capacity and import batches.
- One optional live test passes against Neo4j **5.26.32 Community**, using the official Python driver **6.4.1**. It imports twice, confirms identical counts and runs all five statements in `explore.cypher`. The unit-only test command skips this live test unless connection variables are set.
- A separate source inspection independently reproduced every resident/household/site and internal/boundary edge count above without importing the extraction implementation.
- The raw ZIP passed CRC validation. Its SHA-256 is `e87f5bc0e4f9e6d4ac9a91aeef0cfaa7bc2a82e7a6662762118734f2d871c7c0`. Each of its six extracted source files and each exported file has a checksum in `manifest.json`.
- The disposable local test server was stopped after testing. No connection to the user's Aura account was made. The loader checks the 200,000-node / 400,000-relationship Aura Free limits; available Aura storage was not measured. Aura-specific authentication and a live Aura import remain to be checked using the user's instance.

## Files in this environment

| Location | Purpose |
|---|---|
| `/workspace/geo-synthetic-poverty-network/utah_pilot/` | Extraction/import Python package, CLI, usage guide and Cypher examples. |
| `/workspace/geo-synthetic-poverty-network/tests/` | Fixture and optional live integration tests. |
| `/workspace/geo-synthetic-poverty-network/requirements-utah-pilot.txt` | Isolated pilot dependencies; Python 3.12+. |
| `/workspace/work/ut-reassembled.zip` | Original user-provided archive, reassembled from 19 pieces. |
| `/workspace/work/ut-dataset/ut/` | Full original Utah files; unchanged. |
| `/workspace/work/payson-area-pilot/` | Selected CSVs, outside context, exceptions and manifest. |
| `/workspace/work/payson-independent-counts.json` | Independent source counts. |
| `/workspace/work/payson-live-test-report.json` | Both live import reports and successful query verification. |
| `/workspace/work/utah-python-deps/` | Environment-only installed Python packages. |

## Internet access and downloads

| Source | What was obtained or attempted | Why |
|---|---|---|
| User's connected Drive files | Nineteen `ut-part-*` pieces, reassembled into the 473,416,929-byte ZIP | Retrieve the Utah dataset the user supplied. This was not an additional third-party population dataset. |
| GitHub, this repository | Fetched the published main branch, including updated `AGENTS.md` and approved state-format guide | Start from current repository conventions and preserve previously approved documentation. |
| PyPI (`pypi.org`, `files.pythonhosted.org`) | `neo4j 6.4.1`, `pyproj 3.8.0`, `shapely 2.2.0`, `pytest 9.1.1`, plus dependencies listed below | Python database driver, coordinate conversion, optional boundary selection and tests. |
| PyPI | `pyshp 3.1.6` | Prepared to read the Census shapefile. Installed in the scratch environment, unused in the completed tract pilot and omitted from project requirements. |
| Docker Hub | `neo4j:5.26-community`, serving Neo4j 5.26.32; image digest `sha256:adaa077a3ab023015143b8f73f7076a7d053f12985f5b06f4c6a128c3a2f7240` | Run a disposable local database to test actual Cypher statements, imports and reruns. The image includes its Java/runtime dependencies. |
| US Census | Attempted `https://www2.census.gov/geo/tiger/TIGER2020/PLACE/tl_2020_49_place.zip`; blocked by HTTP 403, including after environment republishing | Obtain a 2020 city polygon so home coordinates could be filtered to exact Payson city limits. **No Census ZIP or boundary file was downloaded or used.** |
| Public documentation via web tools | Read Neo4j quota documentation and Census place/service metadata | Verify limits and identify an appropriate official boundary source; these reads added no population records. |

Additional installed Python dependencies: `certifi 2026.10.23`, `pytz 2026.5`, `iniconfig 2.3.1`, `packaging 26.3`, `pluggy 1.7.0`, `Pygments 2.21.0`. NumPy was already available in the environment. The completed pilot uses only the user's Utah data; software downloads support processing/testing it. Data was not uploaded to Kaggle or Aura.

The active attached runtime continued to report a restricted network policy with `osf.io` as its sole custom allowed host after the user's setup changes. Exact city-limit selection remains pending access to the official boundary; the working tract pilot does not depend on that download.

## Proposed commit for review

One feature commit adding `.gitignore`, `requirements-utah-pilot.txt`, `utah_pilot/` and the three new test files. Existing synthesis code, the approved state-format guide and the existing README remain unchanged. Source and exported datasets stay outside Git. Committing and pushing this prepared change to `pilot/payson-neo4j` require specific user approval under `AGENTS.md`; main is not being changed.
