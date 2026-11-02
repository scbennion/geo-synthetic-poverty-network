# Knowledge graph (Neo4j)

A synthesis run can be loaded into Neo4j as a graph: people, households, places and the
contact networks between people. Each run goes into its own database, named after the run
(`ut-c035` for Salt Lake County, `ut` for all of Utah).

## Model

```
(:Person {id, age, gender})-[:MEMBER_OF]->(:Household {id, htype, size, urban, location})
(:Household)-[:IN_TRACT]->(:Tract {geoid})-[:IN_COUNTY]->(:County {fips})-[:IN_STATE]->(:State {fips, abbreviation})
(:Person)-[:WORKS_AT]->(:Workplace {id, location, placeholder})-[:IN_TRACT]->(:Tract)
(:Person)-[:ATTENDS]->(:School {id, enrolled})
(:Person)-[:ATTENDS]->(:Daycare {id, enrolled})
(:Person)-[:CONTACT {setting}]->(:Person)        // setting: household, school, daycare, work
(:Run {name, state, counties, seed, export_commit, exported_at})
```

- **People**: one node per synthetic person. `age` is in whole years and `gender` is `m` or `f`.
- **Households**: `htype` is the household category from synthesis (0–10 regular household
  types, 11 group quarters; see the README's household table). `size` is the number of members.
  `location` is the home point that all members share, and `urban` says whether it falls in a
  2020 urban area.
- **Workplaces**: workers can work outside the run's counties, so some workplaces have no
  `location` (only the run's own workplaces are placed on roads). `placeholder` is true for the
  `<tract>wNone` IDs synthesis gives to workers whose destination tract has no workplaces.
- **Schools and daycares**: `enrolled` is the number of synthetic children assigned. The site's
  capacity and location come from the education input layer and are not in the run outputs.
- **Adults without a job** have no `WORKS_AT` relationship. In the population file their `wp`
  is their household ID.
- **`CONTACT`** relationships come straight from the network files and are stored once per pair.
  See [Contacts are undirected](#contacts-are-undirected).

### Contacts are undirected

The networks are undirected graphs (`nx.Graph` in `src/create_social_networks.py`). The network
files list each pair twice only because each line is a person followed by all their contacts.
So each contact is stored as **one** `CONTACT` relationship, pointing from the lower person ID
to the higher. That direction means nothing.

Neo4j stores every relationship with a direction, but following it backwards costs the same as
forwards, so a symmetric connection needs only one relationship. Storing both directions would
double the edges and make undirected matches count every pair twice.

```cypher
// All contacts of a person: no arrow
MATCH (p:Person {id: '49035100100i0'})-[:CONTACT]-(q:Person) RETURN q;

// Count each contact once: use an arrow
MATCH ()-[c:CONTACT]->() RETURN c.setting, count(c);
```

- An undirected match on a pair, `MATCH (a)-[c:CONTACT]-(b)`, returns each contact twice (once
  from each end). Use the arrowed form when counting.
- Neo4j Graph Data Science can load `CONTACT` as undirected (`orientation: 'UNDIRECTED'`), so
  it does not need reverse relationships either.
- A connection that really has a direction, such as "A infected B" in a simulation, should be
  a new relationship type, not a second `CONTACT`.

### Why household contacts are stored, not derived

Household networks connect every member only for households of 5 or fewer people. Larger
households (including group quarters) get a Newman–Watts–Strogatz small-world network instead,
the same rule as schools and workplaces (`src/create_social_networks.py` `create_edges`). So
`MEMBER_OF` alone does not give the household contacts.

### Coordinates

Run outputs are labelled EPSG:4269 (NAD83). Neo4j points support WGS-84 but not NAD83, so
locations are stored as WGS-84. The two differ by about a metre in Utah.

## Building a database

The steps below use a Neo4j Desktop 2 DBMS, which runs the Enterprise edition and so can hold
one database per run. The connection settings (`NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`)
live in an env file outside the repo, for example `~/.config/gspn/neo4j.env`.

```bash
# 1. Write the import CSVs to data/neo4j-import/<run>/ (about 20 s for Salt Lake County)
python code/4-knowledge-graph/export_neo4j_csv.py --state ut --counties 035 --seed 42

# 2. Bulk-import into a new database (about 20 s). The DBMS can keep running; the database
#    must not exist yet. <dbms> is the root_path from `neo4j-cli desktop dbms list`, and
#    JAVA_HOME can point at the Java runtime Desktop downloaded (Application/Cache/runtime/...).
<dbms>/bin/neo4j-admin database import full ut-c035 @data/neo4j-import/ut_c035/import.args

# 3. Register the database
neo4j-cli query --env ~/.config/gspn/neo4j.env --database system --rw 'CREATE DATABASE `ut-c035` WAIT'

# 4. Add constraints and indexes (bulk import creates none)
neo4j-cli query --env ~/.config/gspn/neo4j.env --database ut-c035 --rw "$(cat code/4-knowledge-graph/constraints.cypher)"

# 5. Add the tract summary layer (below)
neo4j-cli query --env ~/.config/gspn/neo4j.env --database ut-c035 --rw "$(cat code/4-knowledge-graph/tract_summary.cypher)"
```

To rebuild a run, drop its database first
(`neo4j-cli query ... --database system --rw 'DROP DATABASE `ut-c035``), then repeat steps 2–5.
The full sequence, from raw data to graph, is in [`pipeline.md`](pipeline.md).

## Tract summary layer

The full graph is too big to draw. `code/4-knowledge-graph/tract_summary.cypher` adds a small
layer on top that shows a whole run at once, with tracts as nodes:

```
(:Tract {population, households, workplaces, county, centroid, work_local, contacts_within})
(:Tract)-[:COMMUTES_TO {workers}]->(:Tract)                              home tract -> work tract
(:Tract)-[:CONTACTS_WITH {total, work, school, daycare}]->(:Tract)      lower GEOID -> higher GEOID
```

- These relationships are derived from the person-level graph. Rerun the script after any
  reimport (it deletes the old layer first):
  `neo4j-cli query --env ~/.config/gspn/neo4j.env --database ut-c035 --rw "$(cat code/4-knowledge-graph/tract_summary.cypher)"`
- Same-tract counts are stored on the tract (`work_local`, `contacts_within`) instead of as
  self-loops. Household contacts never cross tracts, so `CONTACTS_WITH` covers work, school
  and daycare only.
- `centroid` is the mean home location, or the mean workplace location for tracts with no
  homes. Tracts outside the run with no placed workplaces have none.
- Salt Lake County: 81,975 `COMMUTES_TO` and 30,879 `CONTACTS_WITH` links. Their totals equal
  the 559,723 workers and the 2,131,849 work, school and daycare contacts.

Both are nearly complete graphs (almost every pair of home tracts shares some contact), so
filter by weight when drawing:

| Filter | Links | Shows |
|---|---|---|
| `COMMUTES_TO` with `workers >= 100` | 508 (238 tracts) | Main commuting corridors |
| `COMMUTES_TO` with `workers >= 200` | 109 | Strongest corridors only |
| `CONTACTS_WITH` with `total >= 250` | 780 | Densest mixing between tracts |
| `CONTACTS_WITH` with `school >= 50` | 544 | School catchments |

## Salt Lake County (`ut-c035`, seed 42)

| Nodes | Count | Relationships | Count |
|---|---|---|---|
| Person | 1,185,222 | CONTACT household | 1,652,730 |
| Household | 405,377 | CONTACT work | 1,328,311 |
| Workplace | 60,700 (32,448 placed in the county) | MEMBER_OF | 1,185,222 |
| Tract | 712 (250 home tracts plus work tracts) | CONTACT school | 599,421 |
| School | 418 | WORKS_AT | 559,723 |
| Daycare | 162 | IN_TRACT | 466,077 |
| County | 28 | ATTENDS | 309,005 |
| State, Run | 1 each | CONTACT daycare | 204,117 |

Checks after import: every person has a household; every pair in a household of 5 or fewer
has a household contact; no household contact links two different households.

## Example queries

```cypher
// Everyone one person meets, by setting
MATCH (p:Person {id: '49035100100i0'})-[c:CONTACT]-(other)
RETURN c.setting, count(*) ORDER BY count(*) DESC;

// Children at the most crowded schools
MATCH (s:School)<-[:ATTENDS]-(k:Person)
RETURN s.id, s.enrolled ORDER BY s.enrolled DESC LIMIT 10;

// Homes within 1 km of a point
MATCH (h:Household)
WHERE point.distance(h.location, point({longitude: -111.891, latitude: 40.761})) < 1000
RETURN count(h), sum(h.size);

// Two-step contacts of a person (contacts of contacts)
MATCH (p:Person {id: '49035100100i0'})-[:CONTACT*2]-(q:Person)
RETURN count(DISTINCT q);
```
