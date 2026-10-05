-- AST-A12 delta to A12_schema.sql (apply after it). Adds versioned geography, conflicts, PIP results and mode separation.
CREATE TABLE boundary_versions (
  boundary_version TEXT PRIMARY KEY,          -- osm:2026-09-22T08:45:51Z | official:<act>:<date>
  city_id TEXT NOT NULL, source_kind TEXT NOT NULL CHECK (source_kind IN ('official','osm_community','derived')),
  snapshot_at TEXT, legal_basis TEXT,         -- act reference if official, else NULL
  geometry_file TEXT NOT NULL, geometry_sha256 TEXT, source_id TEXT REFERENCES sources(source_id), notes TEXT);
CREATE TABLE boundary_crosswalk (             -- only way to move numbers between versions; output rows are kind='derived'
  from_unit TEXT NOT NULL, from_version TEXT NOT NULL, to_unit TEXT NOT NULL, to_version TEXT NOT NULL,
  weight REAL NOT NULL CHECK (weight BETWEEN 0 AND 1),
  method TEXT NOT NULL CHECK (method IN ('identity','area','dasymetric_buildings','dasymetric_population','official_recount')),
  uncertainty TEXT, source_id TEXT, PRIMARY KEY (from_unit, from_version, to_unit, to_version));
CREATE TABLE topology_conflicts (
  conflict_id TEXT PRIMARY KEY, unit_a TEXT NOT NULL, version_a TEXT NOT NULL, unit_b TEXT NOT NULL, version_b TEXT NOT NULL,
  overlap_km2 REAL, repr_lon REAL, repr_lat REAL, status TEXT NOT NULL DEFAULT 'open', resolution TEXT, source_id TEXT);
CREATE TABLE pip_assignments (                -- point-in-polygon results are data with provenance
  object_id TEXT NOT NULL,                    -- osm:node/123 | gtfs:<feed>:stop:<id> | egov:<index>:v<N>:<row>
  boundary_version TEXT NOT NULL, unit_id TEXT, -- NULL when outside
  rule TEXT NOT NULL,                         -- covers_lowest_stable_id_v1
  flag TEXT CHECK (flag IN ('ok','boundary_tie','outside','topology_conflict','swapped_coords')),
  candidates TEXT, computed_at TEXT, tool TEXT, PRIMARY KEY (object_id, boundary_version));
CREATE VIEW game_mode_guard AS                -- synthetic rows must never appear in real analytics views
  SELECT obs_id FROM observations WHERE kind='synthetic';
