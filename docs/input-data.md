# Input data and file formats

This guide covers the sources used by the current pipeline, their preparation, local file handoffs, and the separate published Utah download. Commands are maintained in the [pipeline guide](pipeline.md). Source identities and definitions were checked against the paper and official references on November 9, 2026; historical counts and timings below were not recomputed.

Jump to [sources and preparation](#sources-and-preparation), [local files and handoffs](#local-files-and-handoffs), or [published Utah download](#published-utah-download).

## Sources and preparation

### Census geography and demographic inputs

A **[census tract](https://www.census.gov/programs-surveys/geography/about/glossary.html)** is a relatively permanent statistical subdivision of a county. Tracts generally contain 1,200–8,000 people, with a target around 4,000, but can have fewer or no residents. Their land areas vary; they are not necessarily neighborhoods or cities.

**[Census blocks](https://www.census.gov/programs-surveys/geography/about/glossary.html)** are the smaller units inside tracts. They have no fixed acreage or population size: one may resemble a city block, while a rural block can cover many square miles, and some are unpopulated. Roads, waterways, other features, and legal boundaries can define their edges. Do not treat a block as a fixed walking distance.

A full tract identifier has 11 digits: state (2), county (3), tract (6). A block adds four digits, for 15 total. Keep leading zeros. Sources: [Census geographic identifiers](https://www.census.gov/programs-surveys/geography/guidance/geo-identifiers.html) and [LODES technical documentation](https://lehd.ces.census.gov/data/lodes/LODES8/LODESTechDoc8.0.pdf).

[`download_census_inputs.py`](../code/0-preprocess/prepare-census/download_census_inputs.py) fetches the 2020 Demographic Profile CSV, [2020 TIGER/Line tract boundaries](https://www2.census.gov/geo/tiger/TIGER2020/TRACT/), and urban-area boundaries. [`process_census_shp.py`](../code/0-preprocess/prepare-census/process_census_shp.py) extracts age/sex and household fields from the supplied CSV and joins them to tract geography by `GEOID`. It also accepts previously prepared national input files. Some later helpers select columns by position; preserve the expected field order as well as names.

For a single state the order is:

DP1 comes from the Census API dataset `2020/dec/dp`, `group(DP1)`; its variable names (`DP1_0001C` = count, `DP1_0001P` = percent) are the same as in a data.census.gov table download. The downloader uses the Census API when `CENSUS_API_KEY` is set and otherwise requests the same table through the data.census.gov endpoint. This describes the code path, not a general Census API access policy; the fallback is not a documented public API. The `-work` suffix means `WP_CNT` (workplaces per tract) has been added; the synthesis needs it (`__create_work_location__`), so the demographic-only file cannot stand in for it. The written tract file holds the 12 TIGER attributes, then `DP1_0001C`, `DP1_0025C`, the 18 male age groups, `DP1_0049C`, the 18 female age groups, `DP1_0112C`–`DP1_0146C`, `WP_CNT` and geometry; `create_individuals` now selects its age/sex fields by name, while validation helpers still depend on the prepared column order. See [`code/0-preprocess/census_prep.py`](../code/0-preprocess/census_prep.py).

The paper's [Table 1 and references 21/35](https://doi.org/10.1038/s41597-024-03970-1) identify these sources as the [2020 Census Demographic Profile](https://www.census.gov/data/tables/2023/dec/2020-census-demographic-profile.html) and 2020 tract boundaries. Its reference 22 also identifies [2020 TIGER/Line urban-area boundaries](https://www.census.gov/cgi-bin/geo/shapefiles/index.php?year=2020&layergroup=Urban+Areas), used later for the urban flag.

[`src/settings.py`](../src/settings.py) lists 51 areas: 50 states plus Washington, D.C. Its nonconsecutive geographic codes are identifiers, not entry counts ([Census ANSI/FIPS reference](https://www.census.gov/library/reference/code-lists/ansi.html)).

### Road inputs

The road-download helper points to the **US Census Bureau's [2020 TIGER/Line All Roads files](https://www2.census.gov/geo/tiger/TIGER2020/ROADS/)**, consistent with [paper Table 1 and reference 25](https://doi.org/10.1038/s41597-024-03970-1). These geographic files contain road-line geometry and attributes such as road identifiers and classification codes. They describe roads, not public-transit schedules or observed trips.

`download_and_prepare_road_data` in [`code/0-preprocess/preprocess_data.py`](../code/0-preprocess/preprocess_data.py) selects the county ZIP files for the state, downloads them with TLS certificate checks, and combines them into an intermediate state road file. A failed download stops the run.

The original code cleaned that file with GRASS GIS (geographic-processing software) through a script that hard-coded a macOS install. [`clean_roads.py`](../code/0-preprocess/prepare-road/clean_roads.py) replaces it with Python ([`code/0-preprocess/road_cleaning.py`](../code/0-preprocess/road_cleaning.py)) that approximates the GRASS cleaning steps (`v.clean snap,break,rmdupl` at 0.0001°, then `v.net.components`):

1. Snap vertices that lie within 0.0001° of each other (about 10 m).
2. Split lines where they cross.
3. Drop duplicate geometries within each road class (`MTFCC`).
4. Label connected components: groups of road segments joined to one another (`comp`).

It differs from GRASS in three ways: it snaps vertices only to other vertices (GRASS also snaps them onto nearby segments), it does not remove small angles (`rmsa`), and it de-duplicates per road class where GRASS kept the first feature across classes. Cleaning stays in longitude/latitude so roads keep their exact coincidence with tract boundaries. The output holds `LINEARID`, `MTFCC`, `comp` and geometry in EPSG:4269.

The duplicate-removal choice remains an open input-preparation decision: `clean_road_network(class_column=None)` removes duplicates across classes, matching that aspect of the GRASS behavior. Changing it can affect which roads remain available for workplace placement. It does not resolve the other differences from GRASS.

For Utah (29 counties, 2020) the download takes about 30 s and cleaning about 60 s: 283,754 input features become 790,658 segments in 429 components; the largest component holds 99.7% of segments. Most of the length removed is TIGER duplicates: the same edge listed once per county file or once per route name. The output has not been compared side by side with a GRASS run or the published OSF road files. The synthesis uses these lines for placement, not travel-time estimation.

### Employment inputs

#### Compile home-to-work counts

[`process_lodes8.py`](../code/0-preprocess/prepare-commute-data/process_lodes8.py) calls helpers to download 2020 **LODES** (LEHD Origin-Destination Employment Statistics). **Origin** is the home location; **destination** is the job location.

The paper identifies [2020 LODES 8 and County Business Patterns in Table 1, references 23–24](https://doi.org/10.1038/s41597-024-03970-1). Reference 23 links the [specific CBP source archive](https://www2.census.gov/programs-surveys/cbp/data/2020/CB2000CBP.zip).

Original records connect **home blocks to work blocks**, using `h_geocode` and `w_geocode`. `S000` (S followed by three zeros) counts jobs for that pair and selected job type. This code requests `JT00`, all jobs; one worker can hold multiple jobs, so job totals are not necessarily unique-person totals. These definitions come from the [Census LODES technical documentation](https://lehd.ces.census.gov/data/lodes/LODES8/LODESTechDoc8.0.pdf).

| File type requested | Contents relative to the work state | Example requested filename |
| --- | --- | --- |
| `main` | Home and work are in the same state. | `ut_od_main_JT00_2020.csv.gz` |
| `aux` | The job is in that state; the home is outside it. | `ut_od_aux_JT00_2020.csv.gz` |

The downloader builds these filenames and writes them under `raw-data/work_commute/`, verifying TLS certificates; a failed download stops the run. A state's `aux` file covers incoming workers, not all of its residents' outgoing jobs. Source: [`download_lodes_2020_data`](../code/0-preprocess/preprocess_data.py).

**Out-of-state jobs are not modelled.** A Utah resident's job in Nevada appears only in Nevada's `aux` file, which this pipeline does not read, so those jobs do not contribute to work-destination assignments. Counted from the 2020 `aux` files of every other state (Alaska has none for 2020), Utah residents hold 28,074 out-of-state jobs, 1.9% of their 1,463,937 jobs (Salt Lake County: 1.4%).

To aggregate, the helper replaces each block ID with its parent tract ID, then **adds job counts for identical home-tract/work-tract pairs**. It combines the downloaded `main` and `aux` files and writes `home`, `work`, and summed `S000` to `interim-data/od/<state>-tract-od-2020.csv` (read by the workplace counts) and the same file to `processed-data/od/` (read by the synthesis driver). Block IDs are read as text and zero-padded to 15 digits, so the first 11 digits are the tract for every state. Source: [`combine_in_out_county_data`](../code/0-preprocess/preprocess_data.py).

For example, after aggregation (A, B, and C stand in for tract IDs):

| `home` | `work` | `S000` | Meaning |
| --- | --- | --- | --- |
| A | B | 100 | There are 100 jobs in tract B held by people living in tract A. |
| A | C | 40 | There are 40 jobs in tract C held by people living in tract A. |

Each row is a total for an area pair, not an individual commute or a friendship. The assignment stage uses these totals to select work destinations for synthetic adults from A.

#### Estimate workplace counts

[`process_cbp.py`](../code/0-preprocess/prepare-commute-data/process_cbp.py) reads 2020 **[County Business Patterns](https://www.census.gov/programs-surveys/cbp/about.html)**: by default the paper's pipe-delimited `CB2000CBP.zip` (`--download` fetches it to `raw-data/workplace/`; it is streamed, not unzipped to its 2.7 GB), or a data.census.gov CSV via `--input`. It keeps county geographies only (`GEO_ID` `0500000US…`; the file also has ZIP-code and metro rows whose last five digits can look like a county) and the all-industry (`NAICS2017` 00), all-legal-form (`LFO` 001), all-size (`EMPSZES` 001) row, one per county, with `ESTAB`, the number of business establishments (business sites, not jobs). It writes `interim-data/cbp/workplace_cbp.csv` for all 3,244 counties (Utah: 86,361 establishments).

The intended rule in [`get_number_of_wp`](../code/0-preprocess/preprocess_data.py) is to give a tract the same share of its county's establishments as its share of the county's jobs:

$$
\widehat{B}_t = \left\lfloor B_c \frac{J_t}{J_c} \right\rfloor .
$$

Here $t$ means the tract and $c$ its county. $B$ stands for the number of business establishments; the subscript in $B_t$ means ‘the number in tract $t$.’ The hat in $\widehat{B}_t$ means **an estimate**, rather than a directly observed count. $B_c$ is the county's establishment count, $J_t$ is jobs located in the tract, and $J_c$ is jobs located in that county. Thus the fraction is the tract's share of county jobs, and the brackets mean round down. For example, a tract with 10% of a county's jobs receives 10% of its 1,000 establishments: **100 synthetic workplaces**. This is an estimate, not observed business addresses.

The helper used to divide by the first county's job total for every tract; it now uses the tract's own county. With 2020 Utah data, tract `WP_CNT` sums to 86,018 against 86,361 establishments (the gap is rounding down per tract); before the fix it summed to 10.85 million. [`add_tract_workplaces.py`](../code/0-preprocess/prepare-commute-data/add_tract_workplaces.py) stores the result as `WP_CNT`.

The synthesis also requires `us_tract_number_work.json` with `GEOID`, `WP_CNT`, and `WP_PROBA` (workplace-selection probabilities). [`wp_proba`](../code/0-preprocess/prepare-commute-data/build_tract_workplace_json.py) draws lognormal weights and normalizes them; its comments link workplace-size literature. [`build_tract_workplace_json.py`](../code/0-preprocess/prepare-commute-data/build_tract_workplace_json.py) builds the JSON for one state's tracts plus any out-of-state work tracts in that state's `aux` file (none for Utah, since `aux` work locations are in-state).

### Education inputs

The state driver loads `<state>_school_id.gpkg` and `<state>_daycare_id.gpkg`. [Paper Table 1, Step 2, and reference 20](https://doi.org/10.1038/s41597-024-03970-1) identify the source as the EPA's **[Educational Institutions, US, 2015, ORNL, SEGS](https://catalog.data.gov/dataset/educational-institutions-us-2015-ornl-segs)**, covering schools and daycare. Thus these inputs are dated 2015 while the demographic/commuting inputs are dated 2020. The paper says unique site IDs were added during preprocessing; its exact ID scheme is unknown.

[`build_edu_sites.py`](../code/0-preprocess/prepare-edu/build_edu_sites.py) downloads [`ORNL_Education.zip`](https://edg.epa.gov/data/Public/OEI/ORNL_Education/ORNL_Education.zip) (the 2015 layer, listed on [data.gov](https://catalog.data.gov/dataset/educational-institutions-us-2015-ornl-segs)) and writes both GeoPackages in EPSG:4269:

- **Schools:** the `PublicSchools` and `PrivateSchools` layers. Age bands come from `LEVEL` through the existing helpers.
- **Daycare:** the `DayCareCenters` layer. It has no enrollment field, so `ENROLLMENT` is its `POPULATION` value.
- **Not used:** the two college layers.
- **IDs:** `eduID` is `<state FIPS>s<n>` for schools and `<state FIPS>d<n>` for daycare, numbered in a fixed order; the source ID is kept in `SRC_ID`.
- **Missing enrollment:** negative codes (-1, -2, -9) become `ENROLLMENT` 0 and are flagged in `ENR_MISSING`. Such a site never has room, so children only reach it when every candidate is full.

Utah has 1,218 schools (1,070 public, 148 private; 74 with missing enrollment) and 268 daycares. `--source nces_ccd` is a placeholder for a later replacement source. These files use the paper's cited source but have not been compared with the published GeoPackages.

| Input field | How the assignment code uses it |
| --- | --- |
| `eduID` | Identifier copied into a child's `wp` field. |
| `geometry` | Site location used to search around the home tract. |
| `LATITUDE`, `LONGITUDE` | Site coordinates used to rank candidates by distance from the child's home. |
| `s_age`, `e_age` | Inclusive minimum and maximum ages accepted by a school. The daycare branch does not apply this filter. |
| `ENROLLMENT` | School enrollment or, for daycare, the source `POPULATION` value used as a proxy. Neither is verified building capacity. |
| `count` | Children already enrolled at the start of a run (0 from `build_edu_sites.py`); assignments add to it. |

The school-age helpers in `code/0-preprocess/prepare-edu/build_edu_sites.py` map school `LEVEL` to ages: Primary/Elementary 5–11, Middle 12–14, Secondary 12–17, High 15–17, and other levels 5–17.

Sources: [state input loading](../code/1-population-synthesis/run-synthesis-by-state.py), [school age-range helpers](../code/0-preprocess/prepare-edu/build_edu_sites.py), and [assignment module](../code/1-population-synthesis/assign_education_site.py). School and daycare use separate tables but share the same assignment module.


### Source checks

The paper's [Table 1](https://doi.org/10.1038/s41597-024-03970-1) identifies 2020 Census demographics, tracts, roads, CBP, LODES 8, and urban areas, plus 2015 education sites. The following official references confirm the source identities and relevant definitions:

| Source | Reference checked | Important distinction |
| --- | --- | --- |
| Census DP1 | [2020 DP1 variable definitions](https://api.census.gov/data/2020/dec/dp/groups/DP1.html) | Count fields end in `C`; percent fields end in `P`. These are aggregate statistics. |
| TIGER/Line | [2020 tract files](https://www2.census.gov/geo/tiger/TIGER2020/TRACT/), [road files](https://www2.census.gov/geo/tiger/TIGER2020/ROADS/), [urban-area files](https://www2.census.gov/geo/tiger/TIGER2020/UAC/) | The urban directory includes both `uac20` and its corrected release; the code selects the uncorrected filename. |
| LODES 8 | [Dataset structure, version 8.0](https://lehd.ces.census.gov/data/lodes/LODES8/LODESTechDoc8.0.pdf), OD table | `main` is in-state home/work, `aux` is out-of-state home/in-state work, `JT00` means all jobs, and `S000` counts jobs. |
| CBP | [Program definitions](https://www.census.gov/programs-surveys/cbp/about.html) and [2020 archive listing](https://www2.census.gov/programs-surveys/cbp/data/2020/) | Establishments have paid employees; CBP is not a complete inventory of all businesses or government workplaces. The listing includes `CB2000CBP.zip`, which the code requests. |
| EPA/ORNL education | [Official dataset catalog](https://catalog.data.gov/dataset/educational-institutions-us-2015-ornl-segs) | The dataset is titled 2015; the later metadata update does not establish a newer site vintage. Its layers include public/private schools and daycare. |

The paper was checked using its published PDF in the project Drive folder when the publisher page could not be retrieved. The EPA catalog was accessible, but the legacy EPA metadata/service endpoints could not be retrieved during review. The ZIP link above records the URL used by the preparation code; this review did not download it again. The daycare `POPULATION` mapping is confirmed by the [preparation code](../code/0-preprocess/prepare-edu/build_edu_sites.py), not a claim that the source defines licensed daycare capacity.

The urban-area release remains an open input choice: the code uses `tl_2020_us_uac20.zip`; the directory also offers `tl_2020_us_uac20_corrected.zip` and the 2010-area file `tl_2020_us_uac10.zip`. The paper does not identify which urban-area file it used. Selecting another release would change the input and should be documented separately.

## Local files and handoffs

### Input paths

The data are distributed separately from this checkout. All scripts take their paths from [`src/settings.py`](../src/settings.py): `DATA_DIR` is `<repo>/data` unless the `GSPN_DATA_DIR` environment variable points elsewhere, so scripts can run from any directory.

```text
data/
  raw-data/          # Original census, commuting and other source inputs
  interim-data/      # Intermediate preparation outputs
  processed-data/   # Inputs consumed by population synthesis
    census/
    od/
    road/
    edu/
    urban/
    us_tract_number_work.json
  results-data/     # Generated population, workplace and network outputs
    <state>/
    1-us/           # National worker table and work network
```

For each state, the synthesis driver expects the following names. Here `<state>` is its lowercase abbreviation and `<STATE>` its uppercase abbreviation. These are **code expectations, not a verified OSF file inventory**:

```text
data/processed-data/census/<state>-tracts-demo-work.shp.zip
data/processed-data/od/<state>-tract-od-2020.csv
data/processed-data/road/<STATE>_road_cleaned.shp.zip
data/processed-data/edu/<state>_school_id.gpkg
data/processed-data/edu/<state>_daycare_id.gpkg
data/processed-data/urban/<STATE>_urban.gpkg
data/processed-data/us_tract_number_work.json
```

The JSON supplies destination-tract workplace metadata, including `GEOID`, `WP_CNT`, and `WP_PROBA`, used for cross-tract work assignments. `build_tract_workplace_json.py` writes it for one state at a time, so it holds the last state built.

### Prepared input fields

| Input | Fields consumed and interpretation |
| --- | --- |
| Tracts | `GEOID`, polygon geometry, DP1 demographic/household fields, and `WP_CNT`. The synthesis driver indexes by `GEOID`; the individual generator selects age/sex counts by name, while validation helpers still require the prepared column order. See [Census preparation](input-data.md#census-geography-and-demographic-inputs) for the expected order. |
| Commuting | `home`, `work`: 11-digit tract identifiers; `S000`: aggregate job count for that pair. This is not an individual movement table. |
| Workplace JSON | Newline-delimited records with `GEOID`, `WP_CNT`, and `WP_PROBA`. Positive workplace counts need corresponding selection probabilities. The assignment helper normalizes their sum when necessary. |
| Roads | Line geometry with a CRS and `MTFCC` road class. Synthesis selects local/service roads for homes and secondary roads plus local/service-road endpoints for workplaces. |
| Schools and daycare | `eduID`, site geometry, `LATITUDE`, `LONGITUDE`, `ENROLLMENT`, and initial `count`. Schools also use inclusive `s_age`/`e_age` bounds. See [education input fields](input-data.md#education-inputs). |
| Urban areas | Polygon geometry used to label whether generated home points intersect an urban area. |

Sources: [input loading](../code/1-population-synthesis/run-synthesis-by-state.py), [work assignment](../code/1-population-synthesis/assign_workplace.py), [education assignment](../code/1-population-synthesis/assign_education_site.py), [spatial placement](../code/1-population-synthesis/create_space.py), and [urban classification](../code/1-population-synthesis/create_space.py).

#### Identifiers and coordinates

- Keep geography codes as strings: state FIPS has 2 digits, county FIPS 3, tract GEOID 11, and source LODES block GEOID 15. Preserve leading zeros.
- Generated person IDs start with the home tract GEOID and an `i` suffix; household IDs use `h`, workplace IDs `w`, school IDs `s`, and daycare IDs `d`. Prepared education IDs begin with state FIPS; do not assume every site ID embeds a tract. Shared IDs, not row numbers or GeoPackage `fid`, define joins.
- Run names are lowercase state abbreviations, optionally followed by sorted county codes: `ut` or `ut_c035-049`. The combined worker outputs use `us` for the all-states run, otherwise the selected run name. See [CLI naming](../src/cli.py).
- Roads, prepared education sites, and output points are labeled EPSG:4269 (NAD83 longitude/latitude). Census and urban preparation also produce EPSG:4326 files. Distances for placement and education buffers use Utah-specific EPSG:26912 in metres. These coordinate systems are not interchangeable; see [known CRS gaps](limitations.md#setup-and-file-handoff-gaps).

### Stage handoffs

All output paths below are relative to `RESULTS_DIR` (`data/results-data/` by default). `<run>` follows the naming rules above; `<state>` is lowercase.

| Producer → consumer | File or handoff | Meaning |
| --- | --- | --- |
| Preparation → synthesis | Files under `processed-data/` listed above | State-wide inputs, even when selecting a county |
| Synthesis → contacts/validation | `<state>/<run>_population.gpkg` | People and home locations; the shared [reader](../src/population_io.py) loads this directly |
| Synthesis → export | `<state>/<run>_population.csv` | Required by the existing exporter, but only conditionally written by synthesis; see the export gap below |
| Synthesis → export | `<state>/<run>_workplace.gpkg` | Generated workplace locations, not an observed business inventory |
| Household/education driver → export | `<state>/social_networks/<run>_{household,school,daycare}_network.csv` | Headerless person adjacency lists |
| Household/education driver → work driver | `1-us/<run>_work_population.csv` | Workers selected by age and workplace ID type, with `id`, `age`, `hhold`, and `wp` |
| Work driver → export | `1-us/<run>_work_network.csv` | Headerless worker adjacency list |
| Synthesis → diagnostics/validation | `<state>/<run>_verification.csv`, conditional `<run>_error_log.csv`, and timing CSVs | Counts, failed-tract records, and timing diagnostics; error logs are written when failures occur |
| Export → Neo4j importer | `data/neo4j-import/<run>/` under the configured data root | Node/relationship CSVs and `import.args`; see [graph schema](knowledge-graph.md) and [import instructions](pipeline.md#4-export-the-run-for-neo4j) |

County population reads prefer the county-specific GeoPackage and fall back to filtering the full-state file when it is absent. County selection uses the person's home geography; work destinations can lie outside those counties. Legacy population pickle files are not accepted by the shared reader.

**Export gap:** unlike the contact and validation readers, the [Neo4j exporter](../code/4-knowledge-graph/export_neo4j_csv.py) reads the population CSV directly. It does not fall back to the GeoPackage. Export therefore requires that CSV to exist and match the run; synthesis does not guarantee writing it. This interface discrepancy is documented here for later code work, not fixed in the documentation stage.

Network generation skips existing output files. Do not assume a changed input or seed invalidates that cache; the [pipeline guide](pipeline.md#2-build-the-social-networks) describes rebuilding. Timing outputs vary between runs and must be excluded from scientific-output byte comparisons.

#### Contact CSVs

Each generated row contains a person ID followed by zero or more neighbor IDs, with no header. `A,B,C` represents contacts A–B and A–C. A row containing only A preserves an isolated person. Connections are undirected and unweighted, and reciprocal adjacency rows must not be counted as distinct contacts. All endpoints are person IDs, not resource IDs.

The separately supplied Utah work-network download uses a headered edge list instead. Its format and archive-specific exceptions are documented in [published download formats](input-data.md#published-utah-download); do not apply that layout to locally generated files.

### Population and workplace outputs

The population table describes people and their home locations; a separate workplace table describes synthetic work sites. [`collect_results`](../code/1-population-synthesis/results.py) assembles them, and the [state driver](../code/1-population-synthesis/run-synthesis-by-state.py) writes them under the paths above. A population CSV is written only in the branch handling missing `id` or `wp` values, so it is not a guaranteed handoff. The driver sets a fixed GeoPackage timestamp (`OGR_CURRENT_DATE`, unless already set) to support byte comparisons of repeated runs with identical prepared inputs, environment, and seed.

| Population field | Meaning and construction |
| --- | --- |
| `id` | Synthetic person ID, derived from home tract and an individual suffix. |
| `age`, `gender` | Generated age and `m`/`f` census sex category. |
| `hhold`, `htype` | Household ID and numeric category from membership assignment. |
| `assigned` | Internal household-assignment flag retained in the population output. |
| `wp` | Daytime-location ID: workplace, school, daycare, or a household fallback; not always a job. |
| `geometry` | A **2D [Shapely point](https://shapely.readthedocs.io/en/stable/reference/shapely.Point.html)** generated from road geometry for the home. In this pipeline it has x/y coordinates, not elevation. Shapely can represent a third coordinate, but this code does not generate home elevations. The collector labels the table `EPSG:4269` (NAD83 longitude/latitude) using `set_crs`; [assigning that label does not transform coordinates](https://geopandas.org/en/stable/docs/reference/api/geopandas.GeoDataFrame.set_crs.html), so the inputs must already match. |
| `long`, `lat` | Numeric columns **extracted from the point**: `long = geometry.x`, `lat = geometry.y`. For `POINT (-111.66 40.23)`, they are -111.66 and 40.23. The output direction is road geometry → home point → numeric columns, not the reverse. These columns are copies; they do not automatically change if geometry is transformed later. |
| `urban` | A Boolean **True/False** value. [`check_urban`](../code/1-population-synthesis/create_space.py) returns True if the home point intersects any supplied urban-area geometry, including a boundary intersection; False otherwise. It is not a density category or score. |

The workplace table has `wp` plus its own `geometry`, `long`, and `lat`, assembled with the same coordinate-label/copy behavior. In contrast, a [later validation helper](../code/3-validation/bg_validate_functions.py) can reconstruct points from saved longitude/latitude columns; that reverse operation is separate from output generation.

#### Missing values and placeholders

The writer drops missing person IDs and replaces missing `wp` values with household IDs when that cleanup branch is entered. A household-valued `wp` is not employment. Destination workplace IDs ending in `wNone` mean the destination has no allocated workplaces; `wNotFound` means destination metadata are missing. Preserve these distinctions instead of interpreting them as observed job sites.

School/daycare records with missing enrollment are prepared with `ENROLLMENT = 0` and flagged `ENR_MISSING`; they can still be used as overflow when candidates are full. A failed tract is omitted from the collected population and recorded in the error log. In Neo4j, workers can refer to out-of-county workplaces without located points. See [graph field meanings](knowledge-graph.md#model) for export semantics.

There are no current population fields for wealth, income, spending, or resource-transfer weights. Future integrations need an explicit mapping rather than reinterpreting existing contact or location fields.


## Published Utah download

This section preserves the earlier inspection of the separately supplied Utah archive. Its record counts and missing-value counts are historical observations, not new checks or expectations for a locally generated run. In particular, its workplace count must not be substituted for the corrected local workplace estimate.

### Network CSVs

`id_A`, `id_B`, and `id_C` represent different people's IDs from the population's `id` column. They are explanatory labels, not renamed columns. Neighbor columns are optional.

| CSV file | Header row | Column 1 | Column 2 | Column 3 | Columns 4 onward |
| --- | --- | --- | --- | --- | --- |
| `ut_household_network.csv` | None | `id_A` | `id_B` | `id_C` | More neighbors of `id_A` |
| `ut_school_network.csv` | None | `id_A` | `id_B` | `id_C` | More neighbors of `id_A` |
| `ut_daycare_network.csv` | None | `id_A` | `id_B` | `id_C` | More neighbors of `id_A` |
| `ut_work_network.csv` | `,source,target` | Unnamed export index | `source` = `id_A` | `target` = `id_B` | None |

- **Headerless adjacency list:** data starts immediately; each row contains one person followed by their neighbors. `id_A,id_B,id_C` represents A–B and A–C, not B–C. A person alone on a row has no neighbors.
- **Headered edge list:** the first row names the columns; each subsequent row records one connection. The work file's first column is an export index, not a person ID or weight. Its 592,100 data rows cannot represent people with no edges on their own.

All four CSVs contain **person-to-person connections**, not household or site IDs. The [network methods](methods.md#social-network-generation) and [generator](../code/2-social-networks/create_social_networks.py) describe undirected, unweighted social ties; `source`/`target` do not imply economic-transfer direction. Count repeated adjacency pairs once per network type, and preserve people without connections.

The generator's `to_csv` function writes adjacency lists, including when called by the [national work-network driver](../code/2-social-networks/create_work_networks.py). The supplied Utah work file instead uses an edge list; its conversion/partition code has not been identified.

### Population and location files: additional information

The network CSVs omit demographics, household/site assignments, and coordinates. These are stored separately:

| File | Records | Fields |
| --- | ---: | --- |
| `ut_population.gpkg` | 3,258,960 | `id`, `age`, `gender`, `assigned`, `hhold`, `htype`, `wp`, `urban`, `long`, `lat`, `geom`, `fid` |
| `ut_workplace.gpkg` | 10,515,837 | `wp`, `long`, `lat`, `geom`, `fid` |

A GeoPackage (`.gpkg`) is a SQLite database with geographic metadata. `geom` stores a home/workplace point; `long` and `lat` are its numeric coordinates, labeled **EPSG:4269 (NAD83)**. `fid` is a file-local feature key, not the shared person/site ID.

**School and daycare IDs are saved in `wp`**, as confirmed by the [education-assignment code](../code/1-population-synthesis/assign_education_site.py). Utah examples are `49001100100w85` (workplace), `49001100200s3` (school), and `49021110501d0` (daycare). The workplace table contains only workplace-type `w` IDs; school/daycare coordinates are not supplied in this archive.

The population has one row without a person ID and 887,603 null `wp` values. Preserve these as exceptions/missing values. Workplace rows have unique `wp` IDs, but their count is not a verified count of real businesses or occupied sites.

The archive contains no population/workplace CSV. Their attributes could later be exported to CSV while preserving IDs and coordinate metadata. Income, wealth, and economic-exchange weights are not supplied.

### State download contents

The [paper](https://doi.org/10.1038/s41597-024-03970-1) describes six datasets for each state and Washington, D.C.: population, workplace locations, and the four network types above. Utah's two GeoPackages are under `ut/`; its four CSVs are under `ut/social_networks/`. Other states' exact CSV layouts have not been checked.

