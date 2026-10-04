-- Historical schema reference. The active SQLAlchemy schema is defined in
-- backend/app/models.py and installed through Alembic migrations.
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS formations (
  id BIGSERIAL PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  top_depth DOUBLE PRECISION NOT NULL,
  bottom_depth DOUBLE PRECISION NOT NULL,
  description TEXT
);

CREATE TABLE IF NOT EXISTS wells (
  id BIGSERIAL PRIMARY KEY,
  well_code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  field TEXT NOT NULL,
  location GEOGRAPHY(POINT, 4326) NOT NULL,
  latitude DOUBLE PRECISION NOT NULL,
  longitude DOUBLE PRECISION NOT NULL,
  status TEXT NOT NULL,
  spud_date DATE,
  total_depth DOUBLE PRECISION NOT NULL,
  current_depth DOUBLE PRECISION,
  formation TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_wells_location ON wells USING GIST(location);

CREATE TABLE IF NOT EXISTS surveys (
  id BIGSERIAL PRIMARY KEY,
  well_id BIGINT NOT NULL REFERENCES wells(id) ON DELETE CASCADE,
  measured_depth DOUBLE PRECISION NOT NULL,
  tvd DOUBLE PRECISION NOT NULL,
  inclination DOUBLE PRECISION NOT NULL,
  azimuth DOUBLE PRECISION NOT NULL,
  UNIQUE(well_id, measured_depth)
);
CREATE INDEX IF NOT EXISTS idx_surveys_well_depth ON surveys(well_id, measured_depth);

CREATE TABLE IF NOT EXISTS drilling_events (
  id TEXT PRIMARY KEY,
  well_id BIGINT NOT NULL REFERENCES wells(id) ON DELETE CASCADE,
  depth_start DOUBLE PRECISION NOT NULL,
  depth_end DOUBLE PRECISION NOT NULL,
  formation TEXT NOT NULL,
  event_type TEXT NOT NULL,
  severity TEXT NOT NULL,
  description TEXT NOT NULL,
  cause TEXT NOT NULL,
  mitigation TEXT NOT NULL,
  source_document TEXT NOT NULL,
  source_page INTEGER NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK(depth_end >= depth_start)
);
CREATE INDEX IF NOT EXISTS idx_events_well_depth ON drilling_events(well_id, depth_start, depth_end);
CREATE INDEX IF NOT EXISTS idx_events_type ON drilling_events(event_type);

CREATE TABLE IF NOT EXISTS drilling_parameters (
  id BIGSERIAL PRIMARY KEY,
  well_id BIGINT NOT NULL REFERENCES wells(id) ON DELETE CASCADE,
  timestamp TIMESTAMPTZ NOT NULL,
  depth DOUBLE PRECISION NOT NULL,
  rop DOUBLE PRECISION NOT NULL,
  wob DOUBLE PRECISION NOT NULL,
  rpm DOUBLE PRECISION NOT NULL,
  torque DOUBLE PRECISION NOT NULL,
  standpipe_pressure DOUBLE PRECISION NOT NULL,
  mud_weight DOUBLE PRECISION NOT NULL,
  flow_rate DOUBLE PRECISION NOT NULL,
  pit_volume DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_parameters_well_time ON drilling_parameters(well_id, timestamp DESC);

CREATE TABLE IF NOT EXISTS risk_predictions (
  id TEXT PRIMARY KEY,
  well_id BIGINT NOT NULL REFERENCES wells(id),
  depth DOUBLE PRECISION NOT NULL,
  formation TEXT NOT NULL,
  risk_type TEXT NOT NULL,
  risk_score DOUBLE PRECISION NOT NULL CHECK(risk_score BETWEEN 0 AND 1),
  confidence DOUBLE PRECISION NOT NULL CHECK(confidence BETWEEN 0 AND 1),
  severity TEXT NOT NULL,
  explanation TEXT NOT NULL,
  recommended_review TEXT NOT NULL,
  model_version TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS prediction_evidence (
  id BIGSERIAL PRIMARY KEY,
  prediction_id TEXT NOT NULL REFERENCES risk_predictions(id) ON DELETE CASCADE,
  event_id TEXT NOT NULL REFERENCES drilling_events(id),
  similarity_score DOUBLE PRECISION NOT NULL,
  reason TEXT NOT NULL,
  UNIQUE(prediction_id, event_id)
);

-- Nearby-well candidate query:
-- SELECT well_code, ST_Distance(location, active.location) / 1000 AS distance_km
-- FROM wells CROSS JOIN (SELECT location FROM wells WHERE well_code = $1) active
-- WHERE ST_DWithin(location, active.location, $2 * 1000)
--   AND well_code <> $1
-- ORDER BY distance_km;
