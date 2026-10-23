# State download file formats

## Network CSVs

`id_A`, `id_B`, and `id_C` represent different people's IDs from the population's `id` column. They are explanatory labels, not renamed columns. Neighbor columns are optional.

| CSV file | Header row | Column 1 | Column 2 | Column 3 | Columns 4 onward |
| --- | --- | --- | --- | --- | --- |
| `ut_household_network.csv` | None | `id_A` | `id_B` | `id_C` | More neighbors of `id_A` |
| `ut_school_network.csv` | None | `id_A` | `id_B` | `id_C` | More neighbors of `id_A` |
| `ut_daycare_network.csv` | None | `id_A` | `id_B` | `id_C` | More neighbors of `id_A` |
| `ut_work_network.csv` | `,source,target` | Unnamed export index | `source` = `id_A` | `target` = `id_B` | None |

- **Headerless adjacency list:** data starts immediately; each row contains one person followed by their neighbors. `id_A,id_B,id_C` represents A–B and A–C, not B–C. A person alone on a row has no neighbors.
- **Headered edge list:** the first row names the columns; each subsequent row records one connection. The work file's first column is an export index, not a person ID or weight. Its 592,100 data rows cannot represent people with no edges on their own.

All four CSVs contain **person-to-person connections**, not household or site IDs. The [README](../README.md#2-social-network-generation) and [generator](../src/create_social_networks.py) describe undirected, unweighted social ties; `source`/`target` do not imply economic-transfer direction. Count repeated adjacency pairs once per network type, and preserve people without connections.

The generator's `to_csv` function writes adjacency lists, including when called by the [national work-network driver](../code/2-social-networks/create_work_networks.py). The supplied Utah work file instead uses an edge list; its conversion/partition code has not been identified.

## Population and location files: additional information

The network CSVs omit demographics, household/site assignments, and coordinates. These are stored separately:

| File | Records | Fields |
| --- | ---: | --- |
| `ut_population.gpkg` | 3,258,960 | `id`, `age`, `gender`, `assigned`, `hhold`, `htype`, `wp`, `urban`, `long`, `lat`, `geom`, `fid` |
| `ut_workplace.gpkg` | 10,515,837 | `wp`, `long`, `lat`, `geom`, `fid` |

A GeoPackage (`.gpkg`) is a SQLite database with geographic metadata. `geom` stores a home/workplace point; `long` and `lat` are its numeric coordinates, labeled **EPSG:4269 (NAD83)**. `fid` is a file-local feature key, not the shared person/site ID.

### Shared IDs and attributes

| Field | Meaning and relationship |
| --- | --- |
| `id` | Person ID shared by the population and all network CSV endpoints. |
| `hhold` | Household ID in the population; people with the same value belong to the same modeled household. |
| `wp` | Daytime-location ID in the population: workplace, school, or daycare. Workplace entries join to the workplace table's `wp`. |
| `age`, `gender` | Generated age and Census sex category (`m`/`f`). |
| `htype`, `assigned` | Household category and internal household-assignment flag. |
| `urban` | Whether the modeled home falls in an urban area. |

**School and daycare IDs are saved in `wp`**, as confirmed by the [education-assignment code](../src/assign_education_site.py). Utah examples are `49001100100w85` (workplace), `49001100200s3` (school), and `49021110501d0` (daycare). The workplace table contains only workplace-type `w` IDs; school/daycare coordinates are not supplied in this archive.

The population has one row without a person ID and 887,603 null `wp` values. Preserve these as exceptions/missing values. Workplace rows have unique `wp` IDs, but their count is not a verified count of real businesses or occupied sites.

The archive contains no population/workplace CSV. Their attributes could later be exported to CSV while preserving IDs and coordinate metadata. Income, wealth, and economic-exchange weights are not supplied.

## State download contents

The [paper](https://doi.org/10.1038/s41597-024-03970-1) describes six datasets for each state and Washington, D.C.: population, workplace locations, and the four network types above. Utah's two GeoPackages are under `ut/`; its four CSVs are under `ut/social_networks/`. Other states' exact CSV layouts have not been checked.

## Utah County pilot: proposal only

1. Select residents by the home-tract portion of `id`, using Utah County code [`49049`](https://tigerweb.geo.census.gov/tigerwebmain/Files/acs26/tigerweb_acs26_county_2020_tab20_ut.html).
2. Preserve complete households and referenced daytime locations, including destinations outside the county.
3. Keep connections between selected residents; record cross-boundary connections separately. Deduplicate within each tie type, preserve people with no retained neighbors, and report missing IDs/site references.

No county subset, attribute export, or Neo4j import has been created.
