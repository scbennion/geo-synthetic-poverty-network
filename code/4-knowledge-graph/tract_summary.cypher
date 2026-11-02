// Tract-level summary layer for viewing a whole run at once (see docs/knowledge-graph.md).
// Adds properties to :Tract and two derived relationship types between tracts:
//   (:Tract)-[:COMMUTES_TO {workers}]->(:Tract)          home tract -> work tract
//   (:Tract)-[:CONTACTS_WITH {total, work, school, daycare}]->(:Tract)   lower GEOID -> higher GEOID
// Same-tract counts are stored on the tract (work_local, contacts_within), not as self-loops.
// Safe to re-run: it removes the previous layer first.
// Run: neo4j-cli query --env <env> --database <run-db> --rw "$(cat tract_summary.cypher)"

MATCH (:Tract)-[r:COMMUTES_TO|CONTACTS_WITH]->(:Tract) DELETE r;

MATCH (t:Tract)
CALL (t) {
  OPTIONAL MATCH (t)<-[:IN_TRACT]-(h:Household)
  RETURN count(h) AS households, coalesce(sum(h.size), 0) AS population,
         avg(h.location.longitude) AS hx, avg(h.location.latitude) AS hy
}
CALL (t) {
  OPTIONAL MATCH (t)<-[:IN_TRACT]-(w:Workplace)
  RETURN count(w) AS workplaces, avg(w.location.longitude) AS wx, avg(w.location.latitude) AS wy
}
SET t.households = households, t.population = population, t.workplaces = workplaces,
    t.county = substring(t.geoid, 0, 5),
    t.centroid = CASE WHEN hx IS NOT NULL THEN point({longitude: hx, latitude: hy})
                      WHEN wx IS NOT NULL THEN point({longitude: wx, latitude: wy}) END,
    t.work_local = 0, t.contacts_within = 0;

MATCH (home:Tract)<-[:IN_TRACT]-(:Household)<-[:MEMBER_OF]-(:Person)-[:WORKS_AT]->(:Workplace)-[:IN_TRACT]->(work:Tract)
WITH home, work, count(*) AS workers
CALL (home, work, workers) {
  WITH home, work, workers WHERE home = work
  SET home.work_local = workers
}
CALL (home, work, workers) {
  WITH home, work, workers WHERE home <> work
  CREATE (home)-[:COMMUTES_TO {workers: workers}]->(work)
};

// Separate MATCH clauses: inside one pattern a relationship can be used only once, which would
// drop school/work contacts between members of the same household (both sides share IN_TRACT).
MATCH (a:Person)-[c:CONTACT]->(b:Person)
WHERE c.setting <> 'household'
MATCH (a)-[:MEMBER_OF]->(:Household)-[:IN_TRACT]->(ta:Tract)
MATCH (b)-[:MEMBER_OF]->(:Household)-[:IN_TRACT]->(tb:Tract)
WITH CASE WHEN ta.geoid <= tb.geoid THEN ta ELSE tb END AS t1,
     CASE WHEN ta.geoid <= tb.geoid THEN tb ELSE ta END AS t2, c.setting AS setting
WITH t1, t2, count(*) AS total,
     sum(CASE setting WHEN 'work' THEN 1 ELSE 0 END) AS work,
     sum(CASE setting WHEN 'school' THEN 1 ELSE 0 END) AS school,
     sum(CASE setting WHEN 'daycare' THEN 1 ELSE 0 END) AS daycare
CALL (t1, t2, total) {
  WITH t1, t2, total WHERE t1 = t2
  SET t1.contacts_within = total
}
CALL (t1, t2, total, work, school, daycare) {
  WITH t1, t2, total, work, school, daycare WHERE t1 <> t2
  CREATE (t1)-[:CONTACTS_WITH {total: total, work: work, school: school, daycare: daycare}]->(t2)
};
