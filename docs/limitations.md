# Limitations and known gaps

This guide summarizes current problems and possible remedies. [Methods, validation, and open decisions](methods.md) explains the model and the scientific choices that remain unresolved. Historical counts below come from earlier inspections and runs; they were not recomputed for this documentation revision.

## Modeling and validation gaps

These limitations affect how results can be interpreted. Changing a modeling rule requires a separate decision; reorganizing code should preserve its behavior.

| Gap | Why it matters | Evidence or related decision |
| --- | --- | --- |
| Ages above 89 are not generated | The open-ended Census “85 and older” group is distributed across ages 85–89. Counts are preserved, but the oldest ages are lost. | [Age generation](methods.md#ages-and-sex-categories) |
| Partner ages differ between paper and code | For a male aged 35, the paper's main rule permits females aged 20–40, while the code initially permits 30–50. Single-parent age rules differ too. | [Partner selection](methods.md#member-selection-order-and-partners) |
| Household composition is approximate | Child shortages can lead to adult replacements, and leftover assignments alter household sizes. Explicit parent/child and spouse IDs are not saved. | [Household methods](methods.md#household-membership) |
| Education sites can be overfilled | The model tracks how many children have been assigned to each school or daycare. When every eligible site in the search area is full, it assigns the child to a full site and records the overflow. | [Education assignment and open decisions](methods.md#education-assignment) |
| Daycare participation and site age limit realism | All children aged 0–4 attend daycare, and sites come from 2015 data. The recorded pilot placed 64,059 daycare children and 16,425 school children at full sites; that does not establish observed enrollment or current capacity. | [Pilot results](methods.md#recorded-salt-lake-county-pilot), [education decisions](methods.md#open-decisions-education) |
| Some tracts fail completely | The recorded pilot omitted all 16 residents of tract `49035980000` after eight adults received no household. Successful-tract comparisons exclude those residents. | [Failed-tract decision](methods.md#open-decision-failed-tracts) |
| Interstate jobs are omitted | Utah residents' outgoing jobs require other states' LODES files. The earlier analysis found 1.9% of Utah residents' jobs were outside Utah; those jobs do not contribute to destination assignments. | [Interstate-job decision](methods.md#open-decision-interstate-jobs) |
| Road points approximate locations | Homes and workplaces are placed on selected roads, not observed buildings. Local-road endpoints stand in for workplace intersections. Some comments mention primary roads, but the workplace filter selects secondary roads (`S1200`). | [Road placement](methods.md#road-placement), [placement code](../pipeline/population_synthesis/create_space.py) |
| Social relationships are not independently validated | Existing checks compare demographics, households, and spatial population patterns. They do not establish observed friendships or realistic socioeconomic mixing. | [Validation and interpretation](methods.md#validation) |
| Economic and longitudinal attributes are absent | Generated people have no assigned income, wealth, spending, or mobility history. Contacts are undirected and unweighted. | [Network generation](methods.md#social-network-generation), [intended model assumptions](assumptions.md) |

## Setup and file-handoff gaps

The [changelog](changelog.md) records earlier fixes. The issues below remain documented for future work; these potential solutions have not been implemented by this documentation change.

| Area | Current behavior or problem | Potential solution |
| --- | --- | --- |
| County/full-state repeatability | Tracts share one random stream; geography selection changes which draws reach each tract. | Consider per-tract seeds derived from `(seed, GEOID)`, with an explicit decision about changed outputs. See [reproducibility](methods.md#reproducibility). |
| Unlocked environment | Most versions are unpinned, and the original pilot's library versions were not preserved. | Record and lock a verified environment in a separate setup change. Identical seeds alone cannot guarantee identical outputs across versions. |
| Local-package installation | The requirements file does not install the project automatically. Both `pipeline` and `src` are included in the project package. | Run `python -m pip install -e .` as described in [setup](pipeline.md#setup), then use `python -m pipeline...` from the repository root without a `PYTHONPATH` override. |
| Published pickle files | Network and validation readers accept GeoPackages, not legacy population pickles. | If required, explicitly convert trusted pickle inputs while preserving IDs, fields, and CRS; renaming the extension is not conversion. |
| Census fallback | Without `CENSUS_API_KEY`, the downloader calls an undocumented data.census.gov table endpoint. | Prefer the documented Census API route with a configured key. |
| Utah-only projection | Placement and education buffers use EPSG:26912, which is specific to the Utah pilot. | Choose a suitable projection per target area before using the distance rules elsewhere. |
| Mixed coordinate systems | Tracts and urban files use EPSG:4326; roads, schools, and output points use EPSG:4269. | Select a consistent CRS and transform inputs explicitly before combining them. |
| County road files | County cleaning writes a county-specific file, but synthesis reads the state-wide road filename. | Prepare the full-state road file for the current pipeline; add county-file selection separately if needed. |
| One workplace JSON | `us_tract_number_work.json` is replaced when preparing a different state. | Prepare it for the intended state and preserve that input for repeated runs; consider state-specific files in later code work. |
| Population CSV for export | Synthesis writes it only in the missing-ID/`wp` cleanup branch, while the exporter requires it. | Check that a matching CSV exists before export; later make the writer/exporter agree on a guaranteed population format. See [handoffs](input-data.md#stage-handoffs). |
| Missing tracebacks | Synthesis uses `exc_info=True` with loguru, so tract errors do not include the intended traceback. | Use loguru's exception-recording interface, such as `logger.opt(exception=e)`. |
| Validation modifies input | `load_clean_population_data()` can rewrite the source population GeoPackage, including the full-state file used for a county read. | Keep validation reads separate from cleanup writes and require an explicit output destination. |
| Figure output location | `get_cosine_similarity()` writes `cos_sim_fig.eps` in the current directory. | Give validation figures an explicit results path. |
| Empty road clips | Workplace placement reads the first coordinate of clipped roads; empty clips can cause `IndexError`, including after coordinate transformations. | Filter empty geometries and test boundary/CRS cases before changing placement. |

Source code: [workplace preparation](../pipeline/preprocess/prepare_commute/build_tract_workplace_json.py), [workplace weights](../pipeline/preprocess/prepare_commute/build_tract_workplace_json.py), [synthesis](../pipeline/population_synthesis/run_synthesis_by_state.py), [validation cleanup](../pipeline/validation/after_validation_functions.py), [external validation](../pipeline/validation/external_validation.py), and [spatial placement](../pipeline/population_synthesis/create_space.py).
