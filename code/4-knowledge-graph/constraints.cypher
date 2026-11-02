// Uniqueness constraints and indexes for a run database (bulk import creates none).
// Run: neo4j-cli query --env <env> --database <run-db> --rw "$(cat constraints.cypher)"

CREATE CONSTRAINT person_id IF NOT EXISTS FOR (n:Person) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT household_id IF NOT EXISTS FOR (n:Household) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT workplace_id IF NOT EXISTS FOR (n:Workplace) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT school_id IF NOT EXISTS FOR (n:School) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT daycare_id IF NOT EXISTS FOR (n:Daycare) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT tract_geoid IF NOT EXISTS FOR (n:Tract) REQUIRE n.geoid IS UNIQUE;
CREATE CONSTRAINT county_fips IF NOT EXISTS FOR (n:County) REQUIRE n.fips IS UNIQUE;
CREATE CONSTRAINT state_fips IF NOT EXISTS FOR (n:State) REQUIRE n.fips IS UNIQUE;
CREATE CONSTRAINT run_name IF NOT EXISTS FOR (n:Run) REQUIRE n.name IS UNIQUE;
CREATE INDEX contact_setting IF NOT EXISTS FOR ()-[r:CONTACT]-() ON (r.setting);
CREATE POINT INDEX household_location IF NOT EXISTS FOR (n:Household) ON (n.location);
CREATE POINT INDEX workplace_location IF NOT EXISTS FOR (n:Workplace) ON (n.location);
CALL db.awaitIndexes(600);
