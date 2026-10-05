-- A12 knowledge/data registry schema (SQLite 3; ports to PostgreSQL/PostGIS without changes in semantics)
-- Geometry is NOT stored here: GeoJSON files per boundary_version, referenced by geometry_file + feature id.
PRAGMA foreign_keys = ON;

CREATE TABLE sources (            -- one row per opened document/file/page/API response
  source_id     TEXT PRIMARY KEY,  -- agent-prefixed, e.g. A12-S003; never reused
  canonical_id  TEXT,              -- filled by merge step (cluster id), original id kept
  title TEXT NOT NULL, publisher TEXT, url TEXT NOT NULL,
  published_at  TEXT,              -- ISO date or NULL (unknown)
  accessed_at   TEXT NOT NULL,     -- ISO datetime UTC of actual access
  source_type   TEXT NOT NULL,     -- official_stat|legal_act|registry|api_response|dataset_file|osm|news|repo_file|experiment_log|task_brief
  access_status TEXT NOT NULL,     -- opened|pointer_only|blocked_in_sandbox|not_attempted|restricted
  license TEXT, sha256 TEXT, bytes INTEGER, notes TEXT
);

CREATE TABLE datasets (
  dataset_id TEXT PRIMARY KEY, title TEXT NOT NULL, publisher TEXT,
  landing_url TEXT, download_or_api_url TEXT,
  access_status TEXT CHECK (access_status IN ('sample_verified','page_only','documented_only','restricted','unavailable') OR access_status IS NULL),
  tested_at TEXT, geography TEXT, granularity TEXT, period TEXT, format TEXT,
  license TEXT, auth_requirement TEXT, update_frequency TEXT, notes TEXT
);

CREATE TABLE geo_units (
  unit_id TEXT PRIMARY KEY,        -- kz.<city_slug>.<level>.<unit_slug>   e.g. kz.astana.district.esil
  city_id TEXT NOT NULL,           -- kz.astana | kz.shymkent
  level TEXT NOT NULL,             -- city|district|microdistrict|grid|poi
  parent_id TEXT REFERENCES geo_units(unit_id),
  legacy_id TEXT,                  -- id used by existing product (e.g. 'esil'); never renamed
  name_ru TEXT, name_kk TEXT, name_en TEXT,
  kato_code TEXT, iso_3166_2 TEXT, osm_relation_id INTEGER,
  boundary_version TEXT NOT NULL,  -- <source>:<snapshot>  e.g. osm:2026-09-22T08:45:51Z | official:<act>:<date>
  geometry_source TEXT NOT NULL,   -- official|osm_community|derived|none
  geometry_file TEXT,              -- path to GeoJSON (EPSG:4326, [lon,lat])
  valid_from TEXT, valid_to TEXT,  -- legal validity if known, else NULL
  source_id TEXT REFERENCES sources(source_id)
);

CREATE TABLE indicators (
  indicator_id TEXT PRIMARY KEY,   -- <DIR>.<short>  e.g. ECO.pm25_monthly_mean
  direction TEXT NOT NULL,         -- one of 11 directions
  name_ru TEXT NOT NULL, name_kk TEXT, definition TEXT,
  canonical_unit TEXT NOT NULL,    -- SI-like canonical unit used after conversion
  better TEXT,                     -- higher|lower|neutral
  native_level TEXT,               -- lowest level at which source publishes
  frequency TEXT,                  -- month|quarter|year|irregular|snapshot
  max_age_days INTEGER             -- freshness threshold for 'stale' flag
);

CREATE TABLE observations (        -- long format: one number = one row
  obs_id TEXT PRIMARY KEY,
  indicator_id TEXT NOT NULL REFERENCES indicators(indicator_id),
  unit_id TEXT NOT NULL REFERENCES geo_units(unit_id),
  boundary_version TEXT NOT NULL,
  period_start TEXT NOT NULL, period_end TEXT NOT NULL,
  period_type TEXT NOT NULL,       -- month|quarter|year|ytd|snapshot
  value REAL,                      -- NULL = unknown/not available. 0 only if source states 0
  value_status TEXT NOT NULL CHECK (value_status IN ('reported','reported_zero','missing','suppressed','not_applicable')),
  native_value TEXT, native_unit TEXT,   -- as printed in source
  unit TEXT NOT NULL,              -- canonical unit after conversion
  kind TEXT NOT NULL CHECK (kind IN ('observed','derived','hypothesis','synthetic')),
  derivation TEXT,                 -- formula + input obs_ids when kind=derived
  source_id TEXT NOT NULL REFERENCES sources(source_id),
  locator TEXT NOT NULL,           -- page/table/row/cell or JSON path
  dataset_id TEXT REFERENCES datasets(dataset_id),
  import_id TEXT,                  -- manifest entry that produced the row
  quality_flags TEXT,              -- comma list: stale,unit_converted,boundary_mismatch,ytd,provisional
  CHECK (NOT (value_status='missing' AND value IS NOT NULL)),
  CHECK (NOT (value_status IN ('reported','reported_zero') AND value IS NULL))
);

CREATE TABLE doc_chunks (          -- knowledge base: text is retrieved, numbers live in observations
  chunk_id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(source_id),
  locator TEXT NOT NULL,           -- e.g. 'p.12, section 3.2' | 'article 5, para 2' | 'table 4, row Shymkent'
  lang TEXT, chunk_kind TEXT,      -- text|legal_article|table_caption|table_row
  text TEXT NOT NULL, char_start INTEGER, char_end INTEGER,
  geography TEXT, period TEXT, valid_from TEXT, valid_to TEXT,
  source_sha256 TEXT, extractor TEXT, extracted_at TEXT,
  linked_obs_ids TEXT              -- obs ids produced from this chunk (if any)
);

CREATE TABLE imports (             -- reproducible manifest mirror
  import_id TEXT PRIMARY KEY, dataset_id TEXT, url TEXT, retrieved_at TEXT, http_status INTEGER,
  sha256 TEXT, bytes INTEGER, tool TEXT, command TEXT, output TEXT, rows INTEGER, notes TEXT
);
