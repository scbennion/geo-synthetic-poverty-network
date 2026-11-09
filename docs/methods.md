# Methods, validation, and open decisions

This guide describes the current code, inherited from Jiang et al. (2024) and adapted in this repository. These generated people and contacts are not observed residents or friendships. The intended MVP design is documented separately in [model assumptions](assumptions.md).

Code links establish implementation behavior, not empirical justification. Paper citations preserve the authors' stated rationale; where paper and code differ, both are described. For commands, use the [pipeline guide](pipeline.md).

Start with [population synthesis](#population-synthesis), [network generation](#social-network-generation), [reproducibility](#reproducibility), or [validation](#validation). Open scientific decisions are recorded beside the relevant method; implementation gaps and potential solutions are in [limitations](limitations.md).

## Modeling assumptions

These are rules the code uses to build an artificial population. They describe how the model works, not verified facts about every real household. Separate limitations and paper/code differences follow in [modeling and validation gaps](limitations.md#modeling-and-validation-gaps).

| Topic | Rule in plain language | Evidence |
| --- | --- | --- |
| Age within a five-year group | If Census data report 12 males aged 10–14, the code creates 2 aged 10, 2 aged 11, 2 aged 12, 2 aged 13, and 4 aged 14. The total stays 12; those exact ages are generated, not observed. | [Individual generator](../src/create_individuals.py) |
| Sex categories | People receive the Census categories `m` or `f`; gender identity is not represented. | [Individual generator](../src/create_individuals.py) |
| Household membership | Household types are filled in a fixed order. Members are selected from generated people in the tract, rather than reconstructed from actual families. | [Household coordinator](../src/assign_household.py) |
| Partners | Select a male aged 20+ first. At ages 20–25, select a female aged 18 through his age +15. For older males, use his age −5 through his age +15; if none is available, try any unassigned female aged 20+. Same-sex couples are not generated. | [Partner selection](../src/assign_household.py) |
| Requested children | For couples with children, the random number is centered at **2**; for single-parent categories, at **1.6**. Its standard deviation is 1. After converting to a positive whole number, at least one child is requested. | [Member selection](../src/assign_household.py), [count explanation](#requested-child-and-roommate-counts) |
| Child shortages and roommates | If too few children meet the age rule, the code can select unassigned adults instead. Later assignments of unassigned adults can increase household sizes. | [Member/fallback helpers](../src/assign_household.py) |
| Group quarters | All modeled group-quarters residents in a tract share **one synthetic household ID**, even if real residents live in different dormitories or institutions. Census resident counts are retained as targets; the number and identities of real facilities are not reconstructed. | [Paper, Step 1, p. 3](https://doi.org/10.1038/s41597-024-03970-1), [helper](../src/assign_household.py) |
| One job per selected adult | Each selected adult aged 18+ gets **one workplace ID at most**. The source LODES “all jobs” counts can include multiple jobs per real worker, but this model does not give a person multiple jobs. | [Work assignment](../src/assign_workplace.py), [LODES specification](https://lehd.ces.census.gov/data/lodes/LODES8/LODESTechDoc8.0.pdf) |
| Employment eligibility | Adults are selected without using retirement, labor-force participation, occupation, or income. Someone aged 65+ can be selected; someone aged 18–64 is not guaranteed a job. | [Adult selection](../src/assign_workplace.py) |
| Workplace selection | After choosing a work tract, select a synthetic workplace using supplied workplace probabilities. A helper creates probabilities from a lognormal distribution, allowing unequal workplace sizes. | [Probability helper](../src/tools.py), [workplace selection](../src/assign_workplace.py) |
| Home and workplace locations | Points on selected roads stand in for building locations. Different IDs may share a point. The authors give movement modeling and privacy as reasons for road-based placement. | [Paper, Steps 1–2, pp. 3–4](https://doi.org/10.1038/s41597-024-03970-1), [location generators](../src/create_space.py) |
| Transport conditions | Workplace assignment uses aggregate home/work-area counts, **not calculated travel distances or times**. Construction, closures, congestion, and detours are not modeled. Road geometry is used for placing locations, not planning commutes. | [Work assignment inputs](../src/assign_workplace.py), [location generators](../src/create_space.py) |
| Education participation | All children aged 0–4 are assigned to daycare and all aged 5–17 to school. Schools are selected using age and proximity rules. | [Paper, Step 2, p. 4](https://doi.org/10.1038/s41597-024-03970-1), [age branches](../src/assign_education_site.py) |
| Urban classification | The home is labeled `True` if its point intersects an urban-area polygon and `False` otherwise. | [`check_urban`](../src/tools.py) |
| Social ties | Everyone in groups of five or fewer is connected to everyone else. Larger groups receive a small-world network with mainly local links and some shortcuts. Ties are undirected and have no explicit weights. | [Paper, Step 3, refs. 26–27](https://doi.org/10.1038/s41597-024-03970-1), [edge generation](../src/create_social_networks.py) |

## Population synthesis

[`run-synthesis-by-state.py`](../code/1-population-synthesis/run-synthesis-by-state.py) processes populated tracts: generate people, assign households, generate home points, assign work IDs and workplace points, assign education sites, set urban flags, and collect checks. The following sections follow that sequence.

| Module | Role |
| --- | --- |
| [`src/create_individuals.py`](../src/create_individuals.py) | Generate [ages and sex categories](#ages-and-sex-categories). |
| [`src/assign_household.py`](../src/assign_household.py) | Assign [household membership](#household-membership). |
| [`src/create_space.py`](../src/create_space.py) | Generate [home and workplace points](#road-placement). |
| [`src/assign_workplace.py`](../src/assign_workplace.py) | Use prepared [employment inputs](input-data.md#employment-inputs) to [assign workers](#employment-assignment). |
| [`src/assign_education_site.py`](../src/assign_education_site.py) | Use prepared [education inputs](input-data.md#education-inputs) for [school/daycare assignment](#education-assignment). |
| [`src/tools.py`](../src/tools.py) | Collect [output fields](input-data.md#population-and-workplace-outputs), flag urban residence, and check counts. |

### Ages and sex categories

The input [Census DP1 age/sex counts](https://api.census.gov/data/2020/dec/dp/groups/DP1.json) already use age categories. [`create_individuals`](../src/create_individuals.py) takes 18 groups for each of two sex categories and expands their counts into individual people. For example, if the Census reports 12 males aged 10–14, it creates the following people:

| Generated age | Number of people |
| --- | --- |
| 10 | 2 |
| 11 | 2 |
| 12 | 2 |
| 13 | 2 |
| 14 | 4 |
| **Total** | **12** |

The code first allocates two people to each of the five ages, then puts the two people left over at age 14. The source gives the total of 12, not those exact ages; the code chooses them using this rule.

Thus the grouped input is inherited from Census statistics, rather than the code observing every person's exact age. The implementation needs individual ages for household, adult-work, school, and daycare rules. The authors explain that they chose **hierarchical sampling** because it can use aggregate data without requiring individual microdata and is flexible and computationally efficient. They iterate over the 18 age groups per sex to match Census distributions ([paper Background & Summary, p. 2; Step 1, p. 3; references 18–19 and 21](https://doi.org/10.1038/s41597-024-03970-1)). This is the stated reason for the approach, not evidence for the code's particular choice of exact ages within each Census age group.

The last Census age category is **“85 years and over”**: it combines people aged 85, 86, 90, 100, and any older ages into one total. The code mistakenly treats that open-ended category as if it were the five-year range **85–89**. For example, if the source reports 50 people aged 85+, it generates ten aged 85, ten aged 86, ten aged 87, ten aged 88, and ten aged 89. It still generates 50 people, but none is aged 90 or older. This is a limitation of this implementation, not a statement about real longevity. Its `gender` field holds `m`/`f` census sex categories, not gender identity.

### Household membership

[`__assign_household_order__`](../src/assign_household.py) fills household-type targets with generated people from the same tract. It does not recover actual families or jointly fit household size, relationships, and socioeconomic attributes.

#### Household category targets

`__get_hhold_type__` reads columns from the **[2020 Census Demographic Profile table DP1](https://api.census.gov/data/2020/dec/dp/groups/DP1.json)**. A name such as `DP1_0133C` is a source-table field identifier, not a tunable model parameter: `DP1` identifies the table, `0133` the item, and `C` a count field. In Python, `tract.DP1_0133C` retrieves that field's value for the current tract.

Fields such as `DP1_0113C` follow this naming convention:

| Part | Meaning |
| --- | --- |
| `DP1` | The Census Demographic Profile table containing the statistic. |
| `_0113` | The item identifier within that table; it is a lookup key, not the number of people or households. |
| `C` | A count, rather than a percentage. The category being counted depends on the item. |

The full identifier is the column name in the input data. Its human-readable definition comes from the [Census DP1 variable metadata](https://api.census.gov/data/2020/dec/dp/groups/DP1.json), a dictionary of column names and labels. The category column below explains the household categories used by the code, while the formula column preserves the original Census field names so the calculation can be traced back to its inputs.

The **target-count formula** column below explains how many household slots to create from those input counts. For example, the code interprets `DP1_0133C` as all married-couple households and `DP1_0134C` as the subset with children, so their difference supplies the without-children target. Categories are described according to their interpretation in this code; verify the full source-table labels and definitions when preparing replacement inputs.

| `htype` | Category used by the code | Target-count formula using DP1 input columns |
| --- | --- | --- |
| 0 | Married couple without children | `DP1_0133C - DP1_0134C` |
| 1 | Married couple with children | `DP1_0134C` |
| 2 | Cohabiting couple without children | `DP1_0135C - DP1_0136C` |
| 3 | Cohabiting couple with children | `DP1_0136C` |
| 4 | Male living alone, under 65 | `DP1_0138C - DP1_0139C` |
| 5 | Male living alone, 65 or older | `DP1_0139C` |
| 6 | Male householder with children | `DP1_0140C` |
| 7 | Female living alone, under 65 | `DP1_0142C - DP1_0143C` |
| 8 | Female living alone, 65 or older | `DP1_0143C` |
| 9 | Female householder with children | `DP1_0144C` |
| 10 | Remaining non-family group category | `(DP1_0137C - DP1_0138C - DP1_0140C) + (DP1_0141C - DP1_0142C - DP1_0144C)` |

For example, if a tract has 100 married-couple households and 40 in the with-children category, the targets are 60 type-0 households and 40 type-1 households. These are household counts, not counts of people.

Source for the category calculations: [`__get_hhold_type__`](../src/assign_household.py).

#### Member-selection order and partners

[`__creat_hhold_id__`](../src/assign_household.py) creates household slots and fills types in the order **4, 5, 7, 8, 0, 1, 2, 3, 9, 10, 6**. Living-alone households select matching adults first; subsequent categories draw from those still unassigned.

For couples, [`__htype_find_members__`](../src/assign_household.py) selects a male aged 20+, then an unassigned female:

| Selected male's age $a$ | Initial female age range | Fallback implemented |
| --- | --- | --- |
| 20–25 | 18 through $a+15$ | No broader fallback in this branch; an empty pool can fail. |
| Over 25 | $a-5$ through $a+15$ | If empty, choose from all unassigned females aged **20 through the maximum age in the generated tract population**, inclusive. If this is empty too, selection can fail. |

A male aged 35 can therefore receive a female aged 30–50; males are not required to be older. Same-sex couples are not represented. **The paper differs:** [Table 2, p. 3](https://doi.org/10.1038/s41597-024-03970-1) states that, outside its 20–25 exception, husband's age minus wife's age is between −5 and +15. Algebraically that permits a female age of $a-15$ through $a+5$ (20–40 for a male aged 35), while the code uses $a-5$ through $a+15$ (30–50). Do not silently treat one as the other.

The code’s window allows a female partner to be up to 15 years older but only 5 years younger in the over-25 branch. This can favor older female partners. If the available pool had equal numbers at every age from 30 to 50, the mean female age for a male aged 35 would be 40. The actual available ages are not evenly distributed and earlier assignments remove candidates, so whether females are **usually** older must be measured from generated couples rather than assumed from the window.

Table 2 presents these as assignment assumptions, without attaching a prior-study citation to the specific age windows or documenting the broad female-adult fallback. The code itself also gives no citation for that fallback. A Census families link near child selection does not establish support for partner-age windows. For single-parent households, Table 2 specifies ages 18–64 while the code selects adults aged 18+ without that upper limit.

#### Requested child and roommate counts

The code draws a number, converts its magnitude to a whole count, and requires at least one:

$$
Z \sim \mathcal{N}(\mu,1^2), \qquad
K = \max\left\{1,\left\lfloor |Z| \right\rfloor\right\}.
$$

$Z$ is a normal (bell-shaped) random draw with mean $\mu$ and **standard deviation 1**. $|Z|$ makes it nonnegative; the floor brackets round down; the outer maximum enforces at least one. Draws 0.8, 2.7, and 3.4 request 1, 2, and 3 members. **The mean is not a maximum; there is no fixed upper cap.** The values below are the means of the initial random numbers. Rounding and the minimum of one change the average requested count, and candidate shortages or leftover allocation can change the final household average again.

For a simple illustration, five initial numbers **1.2, 1.6, 2.0, 2.4, 2.8** average exactly **2**. The code converts them to **1, 1, 2, 2, 2**, which average **1.6**. This illustrates why changing the numbers changes their average; it is not an estimate of the model’s overall mean. Child shortages, adult replacements, and later household assignments change final counts further. Also, these parameters apply only to the with-children categories, not to an average over all households, including those without children.

| Household rule | $\mu$ |
| --- | --- |
| Couple with children | 2 |
| Male/female householder with children | 1.6 |
| Additional members of a non-family group | 1.5 |

Child candidates have ages 0 through the smaller of 18 and the youngest selected parent's age minus 18, inclusive. If there are too few, the helper falls back to unassigned adults; later leftover allocation can also change household size. These are requested counts, not guaranteed final parent/child compositions. Sources: [member-count and fallback code](../src/assign_household.py), [NumPy normal-distribution parameters](https://numpy.org/doc/stable/reference/random/generated/numpy.random.normal.html). No verified empirical rationale is supplied here for the chosen means.

#### Group quarters

**[Group quarters](https://www.census.gov/programs-surveys/geography/about/glossary.html)** are communal living arrangements, such as dormitories, nursing facilities, or correctional institutions. `__get_group_quarter__` is the Python helper that selects people for this category.

The institutionalized and non-institutionalized **counts come from the 2020 Census DP1 tract data**, not from random draws. [`process_census_shp.py`](../code/0-preprocess/prepare-census/process_census_shp.py) retains these columns from the input demographic-profile CSV and merges them with tract geography. Their counts are empirical inputs; choosing which synthetic people fill those counts is modeled. The initial age windows below are also code choices, not additional age breakdowns supplied by those four count fields.

After regular households have selected members, the group-quarters helper reads these four tract counts:

| DP1 column | Group interpreted by the code | Initial candidate ages |
| --- | --- | --- |
| `DP1_0127C` | Institutionalized males | 18–64 |
| `DP1_0128C` | Institutionalized females | 18–64 |
| `DP1_0130C` | Non-institutionalized males | 18–100 |
| `DP1_0131C` | Non-institutionalized females | 18–100 |

For each nonzero count, `__get_group_quarter_ids__` randomly selects that many remaining people matching the category's sex and initial age range, without reusing selected people. If that pool is too small, it tries all remaining people of the same sex regardless of age. If even that pool is too small, it returns an empty selection rather than a partial allocation.

Whenever group quarters are represented in a tract, their residents share one synthetic group-quarters household ID. This does not mean that every tract has one real institution, or even has any group-quarters residents. It is an explicit modeling assumption: multiple real facilities are merged because the authors lack facility counts ([paper Step 1, p. 3](https://doi.org/10.1038/s41597-024-03970-1)). For example, residents of two dormitories and a nursing facility within one tract would share one modeled household ID, which can also connect them within the same synthetic household network.

The helper returns selected member lists with the shared ID `<tract>h<regular-household-count>` and category `htype=11`. The main assignment function gives those residents this ID; unselected people proceed to the leftover rules below.

**If the Census input says there are zero regular households:** the code uses a different path. It asks the group-quarters helper for an ID, then gives **every generated person in that tract** that same ID and category 11, instead of trying to form ordinary families. This could represent an institution-only tract. It is not applied to all tracts, and can fail if the helper returns no group-quarters row from which to obtain an ID ([special branch](../src/assign_household.py)).

Sources: [`__get_group_quarter__` and its selection helper](../src/assign_household.py); [Census DP1 definitions](https://api.census.gov/data/2020/dec/dp/groups/DP1.json).

#### Remaining people

`__assign_left_pop_hhold__` first makes a list of households allowed to receive the remaining person. Each household gets the fixed preference weight shown below. It then **divides each weight by the sum of all eligible households’ weights**, making the selection probabilities add up to 1. This is what “normalize” means here; it is not fitting probabilities to a Census distribution:

| Remaining person's age | Eligible household types | Relative weights per household |
| --- | --- | --- |
| Under 18 | 1, 3, 6, 9; fallback to 10 if none exist | 0.45 for 1/3; 0.1 for 6/9 |
| Exactly 18 | 1, 3, 10 | 0.2 for 1/3; 0.6 for 10 |
| Over 18 | 0, 1, 2, 3, 10 | 0.1 for 0/1/2/3; 0.6 for 10 |

For example, suppose a remaining child has only two eligible households: one type 1 with weight 0.45 and one type 6 with weight 0.10. The sum is 0.55, so their selection probabilities are **0.45 ÷ 0.55 ≈ 81.8%** and **0.10 ÷ 0.55 ≈ 18.2%**. More eligible households change that denominator. Census targets influence how many households exist, but the preference weights themselves are fixed in the code, not estimated from Census proportions. Adding these remaining people can change household sizes and composition.

The resulting `hhold` identifier records co-residence. It does not provide explicit parent/child or spouse identifiers for later intergenerational analysis.

After membership is assigned, everyone sharing a household ID receives the same generated home point. See [road placement](#road-placement) for how that point is selected; household composition and geographic placement are separate steps.

Source: [`__assign_left_pop_hhold__`](../src/assign_household.py).

#### Open decision: failed tracts

The recorded Salt Lake County pilot dropped tract `49035980000` (16 people): eight adults received no household, leaving them without home points and causing urban classification to fail. The original code fails the same way. Placing those adults into an existing or new household would change the household model and needs a separate decision; a readability refactor must preserve the existing behavior.

### Employment assignment

[`__assign_workplaces__`](../src/assign_workplace.py) looks up job destinations for each home tract. Let **A** be the number of generated residents aged 18+, and **J** the total jobs assigned to that home tract in the commuting table:

- **If J is greater than A:** all A adults receive **one job each, not multiple jobs**. The code builds a list of destination tracts repeated according to job counts, then randomly selects A entries from that list. For 8 adults and 10 job entries, only 8 entries are assigned, one per adult; the excess 2 jobs are not assigned to anyone. Destinations with more entries are more likely to be selected.
- **If J is at most A:** randomly select J adults, then assign the J job entries among them. Other adults receive no job from this step.

The model therefore gives each adult **at most one workplace ID**, even when the source data count multiple jobs held by the same real person. It does not distinguish retired people, people looking for work, or adults outside the labor force; it samples from all generated adults aged 18+, without matching occupation or income. The source job counts limit how many assignments are made, but do not establish each selected person’s actual employment status.

[`generate_workplace_id`](../src/assign_workplace.py) then selects a synthetic workplace within the destination tract using `WP_CNT` and `WP_PROBA`, producing `<tract>w<number>`. Missing/zero metadata can produce `wNotFound`/`wNone` IDs, which require checking. Workplace ID assignment and [coordinate generation](#road-placement) are separate. **No road-network commute distance is calculated:** the work assignment uses home/work tract counts, while road geometry supplies possible work-site points. It does not account for construction sites, closures, congestion, detours, or route travel time. The historical commuting counts may reflect conditions when collected, but the model does not explicitly simulate those transport conditions.

#### Open decision: interstate jobs

Keep the current in-state scope, or include other states' LODES `aux` files for Utah residents and prepare workplace metadata for those destination tracts. This changes the jobs available for assignment. The earlier analysis recorded 28,074 outgoing jobs statewide (1.9% of residents' jobs; 1.4% for Salt Lake County); these are historical counts, not measurements rerun for this documentation change. See [employment inputs](input-data.md#employment-inputs) for the source definitions.

### Road placement

The authors use road locations as proxies for buildings to support movement modeling and preserve some privacy ([paper Step 1, p. 3](https://doi.org/10.1038/s41597-024-03970-1)). The paper describes approximately 50-meter home spacing and 20-meter workplace spacing, including workplace locations at secondary/residential-road intersections. The implementation uses those spacings, but takes local-road endpoints instead of calculating intersections.

Both location functions in [`src/create_space.py`](../src/create_space.py) use the prepared road dataset and a tract polygon. They select roads intersecting that tract, clip them to its boundary, retain supported line geometries, and remove duplicate coordinate sequences after rounding coordinates to six decimal places. The input `MTFCC` field is the Census **[MAF/TIGER Feature Class Code](https://www.census.gov/library/reference/code-lists/mt-feature-class-codes.html)**, identifying the type of road.

#### Road classes and candidate points

| Road code | Road category | Home candidates | Workplace candidates |
| --- | --- | --- | --- |
| `S1400` | Local neighborhood roads, rural roads, and city streets | Points sampled along the clipped road geometry. | The first coordinate of each clipped geometry. |
| `S1740` | Private roads for service vehicles, such as logging, oil-field, or ranch roads | Same treatment as `S1400`. | Same treatment as `S1400`. |
| `S1200` | Secondary roads | Not selected for homes. | Points sampled along the clipped road geometry. |
| `S1100` | Primary roads | Not selected. | Not selected by the implemented filter, despite comments mentioning primary roads. |

**Homes:** `__create_home_location__` generates candidate points every 50 m (`HOME_SPACING_M`) along the selected `S1400`/`S1740` geometries, starting 50 m in and stopping before the geometry's end. It randomly samples from the pooled candidates. The state driver requests `DP1_0132C + 1` locations: one per regular household slot plus one for the tract's shared group-quarters ID. The returned points are indexed by household ID and mapped onto people's home `geometry` fields.

**Workplaces:** `__create_work_location__` generates candidates every 20 m (`WORK_SPACING_M`) along `S1200` roads, then adds the first coordinate from each selected `S1400`/`S1740` geometry. For a multi-part road, it uses the first coordinate of the first part. Although the variable is called `intersection_points`, the code does not calculate intersections between roads: these are geometry endpoints, which may also lie on the tract boundary after clipping. It samples `WP_CNT` points from the combined pool; local/private-road endpoints can supply locations when secondary-road candidates are unavailable. Points are indexed by workplace ID and saved in the workplace table, separate from people's home coordinates.

#### Placement assumptions and limitations

- Both functions sample **with replacement**: distinct household or workplace IDs can receive identical coordinates. Household members share their household's point by design.
- Spacing is measured in metres: clipped roads are projected to `PLACEMENT_CRS` (EPSG:26912, NAD83 / UTM zone 12N) before interpolation, and points are returned in EPSG:4269. That projection fits Utah only; other states need their own. The original code used `0.0005` and `0.0002` degrees, which in Utah is about 41–56 m and 17–22 m depending on direction.
- Sampling is uniform over pooled candidate points, not over road names, tracts, or parcels. Longer geometries generally contribute more interpolated candidates; workplaces also have the endpoint candidates described above.
- These are synthetic points on roads, not building entrances or observed residential/business addresses. The functions do not check zoning, building footprints, parcel use, or whether a private service road actually has housing.
- There is no general fallback to other road classes or arbitrary points inside the tract. If a function must generate locations but its candidate pool is empty, sampling can fail; inspect tract error logs and resulting coverage.

Sources: [`__create_home_location__` and `__create_work_location__`](../src/create_space.py) and [Shapely interpolation units](https://shapely.readthedocs.io/en/stable/reference/shapely.line_interpolate_point.html).

### Education assignment

The [shared assignment module](../src/assign_education_site.py) uses the prepared school/daycare tables:

The [paper's Step 2, p. 4](https://doi.org/10.1038/s41597-024-03970-1) explicitly states the assumed groups: daycare 0–4, elementary 5–11, middle 12–14, and high school 15–17. The code derives school age bands from site `LEVEL` values, including a Secondary 12–17 branch.

1. Send ages 5–17 to schools and ages 0–4 to daycare. This assumes universal participation in those age ranges.
2. Search around the **whole home tract polygon**, expanding its boundary outward by 11 km (`NEAR_BUFFER_M`). If no eligible sites are found, repeat with 100 km (`FAR_BUFFER_M`). This is a search area around a tract, not a travel radius around the child's home.
3. For schools, also require the child's age to lie between `s_age` and `e_age`; daycare uses no corresponding age-range filter.
4. Rank candidates by distance from the child's home and choose the nearest that still has room (`count < ENROLLMENT`), then add the child to its count. If every candidate is full, choose one at random anyway and log it with the tract and age. An empty candidate pool raises an error and the tract fails.
5. Copy the chosen `eduID` to the child's `wp` field for later network grouping.

The buffers are built in metres after projecting to EPSG:26912 (Utah only). The original code buffered by `0.1` and `0.9` **degrees**; north–south those are about 11 km and 100 km, the values used now. East–west, at Utah's latitude, the old buffers reached only about 8.4 km and 76 km, so the metric buffers reach slightly more sites ([GeoPandas buffer units](https://geopandas.org/en/stable/docs/reference/api/geopandas.GeoSeries.buffer.html), [USGS on degree distances](https://www.usgs.gov/faqs/how-much-distance-does-degree-minute-and-second-cover-your-maps)).

**Capacity:** the driver builds one counter per site table for each state run and passes it to every tract, so places taken in one tract are gone for the next. If a tract fails, the places its children took are given back. Tracts are processed in GEOID order, so earlier tracts get first pick of nearby sites. When every site within 11 km is full, the child goes to one of those full sites; the search does not widen to 100 km. Schools and daycares keep separate counters. The driver logs the number of over-capacity assignments per state. School boundaries, household childcare choices, and observed enrollment histories are not modeled.

#### Open decisions: education

The assignment rules above are implemented; the alternatives below remain undecided:

- **Participation and overflow:** retain universal daycare attendance for ages 0–4, model an attendance share, or change which full site receives overflow. These are different modeling decisions. The current 11 km candidate pool is not widened when it is full.
- **Site age and coverage:** keep the 2015 data or replace/supplement it. `--source nces_ccd` remains a stub. Public schools marked closed or future are currently included (the earlier Utah inspection counted 25 and 24 respectively), along with private schools and sites of unknown/other level. Grade fields could provide tighter age bands, but using them changes eligibility rules.
- **Missing enrollment:** retain the zero-enrollment preparation rule, omit those sites, or estimate enrollment using other attributes. Daycare `POPULATION` is a proxy; it has not been established as licensed capacity.
- **State borders and duplicate IDs:** only in-state sites are considered. Schools and daycares have separate counters, so an ID appearing in both tables would be counted separately.

These options are preserved from the October 27, 2026 decision notes. They have not been implemented by this documentation revision. Recorded overflow counts are in the [pilot results](#recorded-salt-lake-county-pilot).

## Social-network generation

A **node** represents a person; an **edge** represents a modeled connection. [`create_network`](../src/create_social_networks.py) groups people by `hhold` for households or `wp` for work/school/daycare. Groups of at most five connect every pair. Larger groups use [`newman_watts_strogatz_graph(n, 4, 0.3)`](https://networkx.org/documentation/stable/reference/generated/networkx.generators.random_graphs.newman_watts_strogatz_graph.html): four initial neighbors per person on a ring, plus random shortcuts. This applies to households too ([edge-generation code](../src/create_social_networks.py)). The network drivers take `--seed`, so each network file depends only on its input and the seed.

School, daycare and work members are picked by the letter after any leading digits of `wp` (`s`, `d` or `w`; [`wp_kind`](../src/create_social_networks.py)). The original code tested whether that letter appeared anywhere in the ID, so a worker whose workplace was not found (`<tract>wNotFound`) was placed in the daycare network.

Connections are undirected with no explicit weights. The [household/education driver](../code/2-social-networks/create_edu_hhold_get_work_pop.py) writes separate relationship files and collects workers; the [work driver](../code/2-social-networks/create_work_networks.py) groups workers nationally, allowing cross-state coworkers. [`to_csv`](../src/create_social_networks.py) writes headerless adjacency lists: one person ID followed by neighbor IDs. The household/education driver reads the population GeoPackage and writes `results-data/<state>/social_networks/<run>_{household,school,daycare}_network.csv`; the worker table and work network go to `results-data/1-us/<run>_work_population.csv` and `<run>_work_network.csv`, where `<run>` is `us` for an all-states run. These are generated relationships, not observed friendships.

For the modeling rationale, [paper Step 3, p. 4](https://doi.org/10.1038/s41597-024-03970-1) cites Watts and Strogatz (1998; reference 26) for small-world networks and Dunbar (1998; reference 27) for a five-person core group. It explicitly sets $k=4$ to give four neighbors plus the individual and $p=0.3$ to add shortcut variation. Those are the authors' stated choices, not evidence that every real household or workplace follows that network model.


## Reproducibility

Synthesis seeds Python's global `random` and passes a NumPy generator through several drawing steps. Household and education functions still use Python's global generator. Changing to independent generators or changing the order of draws can change assignments even if the seed is unchanged.

All tracts share a random stream and run in GEOID order. County-only and full-state runs therefore need not produce the same people for a given tract. Deriving per-tract seeds from `(seed, GEOID)` is an option, but would change existing outputs. Individual ages are shuffled using the run generator; passing `rng=None` to the individual generator restores its original fixed shuffle seed of 123.

The workplace-weight preparation driver seeds `np.random`, but `wp_proba()` creates an unseeded `default_rng()` unless passed a generator. Rebuilding `us_tract_number_work.json` is therefore not repeatable from `--seed` alone. Earlier two-run comparisons reused that JSON; they do not demonstrate repeatability from freshly downloaded inputs. See [potential engineering solutions](limitations.md#setup-and-file-handoff-gaps).

Matching scientific outputs requires the same prepared inputs, seed, processing order, and library versions. Most dependencies are unpinned; the versions for the original Salt Lake runs were not preserved. The October 27 environment notes record pandas 3.1, NumPy 2.5, NetworkX 3.7, and GeoPandas 1.2 for a later rebuilt environment, not for the original pilot. Timing diagnostics vary and must be excluded from byte comparisons.

## Validation

### Methods reported in the paper

The [Technical Validation section, pp. 5–10](https://doi.org/10.1038/s41597-024-03970-1) reports internal checks of total population, age/sex categories, household totals/types, and tract-level average household size, using **total absolute error** and **absolute percentage difference**. These describe error magnitude and error relative to a reference count. The paper cites its references 14 and 18 for population-synthesis validation methods.

It then compares demographic-count vectors with **2022 ACS PUMS** by 2020 PUMA boundaries using cosine similarity, and compares generated and reference block-group population ranks using Spearman correlation. The paper explains its PUMS year choice by the switch from 2010 to 2020 PUMA geography ([pp. 9–10; reference 30](https://doi.org/10.1038/s41597-024-03970-1)). Its reported outcomes are historical study results, not checks rerun for this fork. The implementation summary below identifies what the available scripts actually calculate.

### Demographic and household checks

| Check | What the code compares | Source |
| --- | --- | --- |
| Per-tract verification | Generated total, sex/age-bin, and household-type counts against DP1 inputs; differences are saved for each successful tract. | [`verify_population`](../src/tools.py) |
| Age/sex distributions | Generated bin totals against both all input tracts and a subset excluding logged failures; writes tables and plots. | [Population validation driver](../code/3-validation/validation_population.py), [aggregation](../src/after_validation_functions.py) |
| Household category totals | Unique generated household IDs by types 0–10 against Census-derived targets; group quarters are not among those 11 plotted categories. | [Household driver](../code/3-validation/validation_hhold.py), [comparison helper](../src/verification.py) |
| Average household size | Per-tract generated people / unique household IDs, compared with DP1 total population / regular household count. The differing handling of group quarters needs review before interpreting this as average regular-household size. | [Size helper](../src/after_validation_functions.py), [driver](../code/3-validation/validation_tract_avg_hhold.py) |

The support module also defines mean absolute error and root mean squared error helpers: average error magnitude and a measure giving more weight to large errors. Their presence does not mean every driver calls them ([metric helpers](../src/after_validation_functions.py)).

### External comparisons

**[PUMS](https://www.census.gov/programs-surveys/acs/microdata.html)** means **Public Use Microdata Sample**. Here it refers to anonymous person/housing-unit records from the **American Community Survey (ACS)**. These are a sample of real survey responses, not a complete list of residents and not the generated synthetic people. Public records omit precise identifying locations. **PUMA** means **Public Use Microdata Area**, the larger geographic area attached to those records; PUMS is the sample, while PUMA is its geography.

The paper uses 2022 ACS PUMS to compare age/sex patterns after grouping both datasets into the same PUMAs. Survey weights are needed to interpret sample records as population estimates; the checked-in PUMS aggregation helper counts rows without applying person weights, so its raw totals should not be described as complete population totals ([aggregation code](../src/external_validation.py)).

- **Age/sex similarity:** aggregate synthetic and Public Use Microdata Sample records by **[PUMA](https://www.census.gov/programs-surveys/geography/guidance/geo-areas/pumas.html)** (a larger statistical area), then calculate cosine similarity of their demographic-count vectors. This measures alignment of the vectors, not equality of population totals. Sources: [driver](../code/3-validation/validation_external_cosine.py), [helpers](../src/external_validation.py), [cosine-similarity definition](https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.distance.cosine.html).
- **Spatial population agreement:** spatially join generated home points to block groups, count residents, and compare ranks of generated counts and supplied ACS population counts using Spearman correlation within each tract. A block group contains multiple blocks within a tract. Sources: [Census geography definitions](https://www.census.gov/programs-surveys/geography/about/glossary.html), [driver](../code/3-validation/validation_external_sc_bg.py), [point counting](../src/bg_validate_functions.py), [Spearman definition](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.spearmanr.html).

### Coverage and interpretation

These describe methods implemented in scripts, **not results obtained in this documentation task**. All validation drivers read the population GeoPackage and accept `--state`/`--counties`; with no options they cover all 51 areas. The original average-size driver stopped after the first two configured states, and failed tracts were never excluded from the "good census" comparisons because their IDs were read as numbers; both are fixed. Check inputs, years, geographic alignment, missing areas, and script completion before interpreting results.

Input-matching checks establish consistency with construction targets; they do not independently validate actual families, friendships, socioeconomic mixing, or mobility. Report failed-tract coverage alongside comparisons that exclude failures. The spatial helper drops missing counts after its join, so zero/missing-area handling also needs review before interpreting correlation. Sources: [error handling](../code/1-population-synthesis/run-synthesis-by-state.py), [failed-tract filtering](../src/after_validation_functions.py), [spatial merge](../src/bg_validate_functions.py).


## Recorded Salt Lake County pilot

**Recorded pilot (Salt Lake County, seed 42, 2026-10-23):** the previous documentation reports two end-to-end runs with identical outputs (18 files). These results were not rerun for this documentation change. Later timing diagnostics vary between runs and must be excluded from byte comparisons. See [optimization notes](optimization.md) for later estimates and their limits.

- **Tracts:** 250 of 251 succeeded. Tract `49035980000` (16 people) failed because 8 adults received no household.
- **Population and households:** 1,185,222 people. Age/sex and household-type totals equal DP1 for the successful tracts.
- **Workers:** 559,723.
- **Over-capacity placements:** 64,059 children aged 0–4 at full daycares, and 16,425 children at full schools in 20 fast-growing tracts.
- **Run time:** synthesis needs about 32 minutes of compute (about 7.5 s per tract); networks and validation about 1 minute. Keep the machine awake: macOS sleep, including a closed lid, pauses the run.

Details are in [`changelog.md`](changelog.md).


## Environment history

The requirements now specify Notebook 6.5.7. During cloud setup, the former 6.5.6 pin required `pyzmq<25`, whose source build failed on the available Python 3.12/compiler combination. Notebook 6.5.7 allowed current ZeroMQ wheels and passed notebook startup and kernel checks. This resolves that specific dependency issue; the environment is not fully locked; see [open decisions](methods.md#reproducibility).


## Resolved issues and further decisions

The earlier open-decision notes identify these issues as resolved: leading zeros lost from GEOIDs, `wNotFound` workplace IDs accidentally matching daycare, working-directory-dependent commuting paths, and validation readers ignoring county-specific run names. Their history remains in the [changelog](changelog.md).

Current implementation problems and possible remedies are maintained in [limitations](limitations.md), including workplace-weight seeding, tracebacks, CRS alignment, and file handoffs. Before a full Utah run, the earlier notes prioritized workplace-weight seeding and error tracebacks, followed by decisions about jobs and education. Before modeling another state, resolve the Utah-specific projection.
