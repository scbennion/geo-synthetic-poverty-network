// In Neo4j Query / Browser, set dataset_id to the value in manifest.json:
// :param dataset_id => 'copy-the-dataset-id-here'
// Run each statement separately. Small LIMITs keep the visual view readable.

// Residents by age band. These are synthetic attributes.
MATCH (p:PilotPerson {dataset_id: $dataset_id})
RETURN toInteger(p.age / 10) * 10 AS age_band, count(*) AS residents
ORDER BY age_band;

// Daytime destinations, including school and daycare sites without coordinates.
MATCH (p:PilotPerson {dataset_id: $dataset_id})-[:DAYTIME_AT]->(s:PilotSite)
RETURN s.site_type AS site_type, count(DISTINCT s) AS sites, count(p) AS residents
ORDER BY residents DESC;

// A small social neighborhood; use an ID from population.csv.
// :param person_id => 'copy-a-person-id-here'
MATCH (p:PilotPerson {dataset_id: $dataset_id, id: $person_id})
OPTIONAL MATCH (p)-[r:HOUSEHOLD_TIE|WORK_TIE|SCHOOL_TIE|DAYCARE_TIE]-(q:PilotPerson)
RETURN p, r, q LIMIT 60;

// Social degree only: membership relationships would change this measure.
MATCH (p:PilotPerson {dataset_id: $dataset_id})
OPTIONAL MATCH (p)-[r:HOUSEHOLD_TIE|WORK_TIE|SCHOOL_TIE|DAYCARE_TIE]-()
WITH p, count(r) AS degree
RETURN min(degree) AS minimum, avg(degree) AS mean,
       percentileCont(degree, 0.5) AS median, max(degree) AS maximum;

// Household membership and a sample of referenced destinations.
MATCH (h:PilotHousehold {dataset_id: $dataset_id})<-[:LIVES_IN]-(p:PilotPerson)
OPTIONAL MATCH (p)-[r:DAYTIME_AT]->(s:PilotSite)
RETURN h, p, r, s LIMIT 60;
