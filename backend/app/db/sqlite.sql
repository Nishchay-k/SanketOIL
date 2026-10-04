PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS wells (
  id INTEGER PRIMARY KEY,
  well_code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  field TEXT NOT NULL,
  latitude REAL NOT NULL,
  longitude REAL NOT NULL,
  status TEXT NOT NULL,
  spud_date TEXT,
  total_depth REAL NOT NULL,
  current_depth REAL,
  formation TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS formation_intervals (
  id INTEGER PRIMARY KEY,
  formation TEXT NOT NULL UNIQUE,
  top_depth REAL NOT NULL,
  bottom_depth REAL NOT NULL,
  description TEXT
);

CREATE TABLE IF NOT EXISTS surveys (
  id INTEGER PRIMARY KEY,
  well_id INTEGER NOT NULL REFERENCES wells(id) ON DELETE CASCADE,
  measured_depth REAL NOT NULL,
  tvd REAL NOT NULL,
  inclination REAL NOT NULL,
  azimuth REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS drilling_events (
  id TEXT PRIMARY KEY,
  well_id INTEGER NOT NULL REFERENCES wells(id) ON DELETE CASCADE,
  depth_start REAL NOT NULL,
  depth_end REAL NOT NULL,
  formation TEXT NOT NULL,
  event_type TEXT NOT NULL,
  severity TEXT NOT NULL,
  description TEXT NOT NULL,
  cause TEXT NOT NULL,
  mitigation TEXT NOT NULL,
  source_document TEXT NOT NULL,
  source_page INTEGER NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS drilling_parameters (
  id INTEGER PRIMARY KEY,
  well_id INTEGER NOT NULL REFERENCES wells(id) ON DELETE CASCADE,
  timestamp TEXT NOT NULL,
  depth REAL NOT NULL,
  rop REAL NOT NULL,
  wob REAL NOT NULL,
  rpm REAL NOT NULL,
  torque REAL NOT NULL,
  standpipe_pressure REAL NOT NULL,
  mud_weight REAL NOT NULL,
  flow_rate REAL NOT NULL,
  pit_volume REAL NOT NULL,
  source TEXT NOT NULL DEFAULT 'development'
);

CREATE TABLE IF NOT EXISTS risk_predictions (
  id TEXT PRIMARY KEY,
  well_id INTEGER NOT NULL REFERENCES wells(id),
  depth REAL NOT NULL,
  formation TEXT NOT NULL,
  risk_type TEXT NOT NULL,
  risk_score REAL NOT NULL,
  confidence REAL NOT NULL,
  severity TEXT NOT NULL,
  explanation TEXT NOT NULL,
  recommended_review TEXT NOT NULL,
  model_version TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prediction_evidence (
  id INTEGER PRIMARY KEY,
  prediction_id TEXT NOT NULL REFERENCES risk_predictions(id) ON DELETE CASCADE,
  event_id TEXT NOT NULL REFERENCES drilling_events(id),
  similarity_score REAL NOT NULL,
  reason TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY,
  original_name TEXT NOT NULL,
  stored_name TEXT NOT NULL,
  media_type TEXT NOT NULL,
  extension TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  extraction_status TEXT NOT NULL,
  extraction_note TEXT NOT NULL,
  extracted_text TEXT NOT NULL DEFAULT '',
  entities_json TEXT NOT NULL DEFAULT '{}',
  well_id INTEGER REFERENCES wells(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS document_chunks (
  id INTEGER PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL,
  source_page INTEGER,
  content TEXT NOT NULL,
  UNIQUE(document_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS extracted_entities (
  id INTEGER PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  entity_type TEXT NOT NULL,
  entity_value TEXT NOT NULL,
  normalized_value TEXT NOT NULL DEFAULT '',
  source_page INTEGER,
  confidence REAL NOT NULL,
  context TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS extracted_events (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  well_id INTEGER REFERENCES wells(id) ON DELETE SET NULL,
  well_code TEXT NOT NULL DEFAULT '',
  depth_start REAL,
  depth_end REAL,
  formation TEXT NOT NULL DEFAULT '',
  event_type TEXT NOT NULL,
  severity TEXT NOT NULL DEFAULT 'UNKNOWN',
  description TEXT NOT NULL,
  cause TEXT NOT NULL DEFAULT '',
  mitigation TEXT NOT NULL DEFAULT '',
  source_page INTEGER,
  extraction_method TEXT NOT NULL,
  extraction_confidence REAL NOT NULL,
  review_status TEXT NOT NULL DEFAULT 'PENDING',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reservoir_properties (
  id INTEGER PRIMARY KEY,
  well_id INTEGER NOT NULL REFERENCES wells(id) ON DELETE CASCADE,
  formation TEXT NOT NULL,
  depth_start REAL NOT NULL,
  depth_end REAL NOT NULL,
  lithology TEXT NOT NULL,
  porosity_percent REAL,
  permeability_md REAL,
  pressure_context TEXT NOT NULL DEFAULT '',
  source_document TEXT NOT NULL DEFAULT '',
  source_page INTEGER,
  UNIQUE(well_id, formation, depth_start, depth_end)
);

CREATE TABLE IF NOT EXISTS mud_programs (
  id INTEGER PRIMARY KEY,
  well_id INTEGER NOT NULL REFERENCES wells(id) ON DELETE CASCADE,
  formation TEXT NOT NULL,
  depth_start REAL NOT NULL,
  depth_end REAL NOT NULL,
  fluid_type TEXT NOT NULL,
  mud_weight_min REAL,
  mud_weight_max REAL,
  source_document TEXT NOT NULL DEFAULT '',
  source_page INTEGER,
  UNIQUE(well_id, formation, depth_start, depth_end)
);

CREATE TABLE IF NOT EXISTS casing_programs (
  id INTEGER PRIMARY KEY,
  well_id INTEGER NOT NULL REFERENCES wells(id) ON DELETE CASCADE,
  casing_size TEXT NOT NULL,
  setting_depth REAL NOT NULL,
  casing_type TEXT NOT NULL DEFAULT '',
  source_document TEXT NOT NULL DEFAULT '',
  source_page INTEGER,
  UNIQUE(well_id, casing_size, setting_depth)
);

CREATE TABLE IF NOT EXISTS cementing_records (
  id INTEGER PRIMARY KEY,
  well_id INTEGER NOT NULL REFERENCES wells(id) ON DELETE CASCADE,
  event_id TEXT REFERENCES drilling_events(id) ON DELETE SET NULL,
  formation TEXT NOT NULL DEFAULT '',
  depth_start REAL,
  depth_end REAL,
  summary TEXT NOT NULL,
  mitigation TEXT NOT NULL DEFAULT '',
  source_document TEXT NOT NULL DEFAULT '',
  source_page INTEGER
);

CREATE TABLE IF NOT EXISTS model_versions (
  model_version TEXT PRIMARY KEY,
  model_type TEXT NOT NULL,
  status TEXT NOT NULL,
  training_dataset_version TEXT NOT NULL,
  feature_names_json TEXT NOT NULL DEFAULT '[]',
  metrics_json TEXT NOT NULL DEFAULT '{}',
  artifact_path TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS alerts (
  id TEXT PRIMARY KEY,
  well_id INTEGER NOT NULL REFERENCES wells(id) ON DELETE CASCADE,
  prediction_id TEXT REFERENCES risk_predictions(id) ON DELETE SET NULL,
  timestamp TEXT NOT NULL,
  risk_type TEXT NOT NULL,
  severity TEXT NOT NULL,
  confidence REAL NOT NULL,
  trigger_reason TEXT NOT NULL,
  supporting_evidence TEXT NOT NULL DEFAULT '[]',
  recommendation TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'NEW' CHECK(status IN ('NEW','ACKNOWLEDGED','RESOLVED')),
  acknowledged_at TEXT,
  resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_well_depth
  ON drilling_events(well_id, depth_start, depth_end);
CREATE INDEX IF NOT EXISTS idx_events_type
  ON drilling_events(event_type);
CREATE INDEX IF NOT EXISTS idx_surveys_well_depth
  ON surveys(well_id, measured_depth);
CREATE INDEX IF NOT EXISTS idx_parameters_well_time
  ON drilling_parameters(well_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_document_chunks_document
  ON document_chunks(document_id, chunk_index);
CREATE INDEX IF NOT EXISTS idx_extracted_events_well_depth
  ON extracted_events(well_id, depth_start, depth_end);
CREATE INDEX IF NOT EXISTS idx_extracted_entities_document
  ON extracted_entities(document_id, entity_type);
CREATE INDEX IF NOT EXISTS idx_alerts_well_status
  ON alerts(well_id, status, timestamp);
CREATE UNIQUE INDEX IF NOT EXISTS idx_cementing_event
  ON cementing_records(event_id) WHERE event_id IS NOT NULL;
