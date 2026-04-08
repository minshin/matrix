-- Matrix schema bootstrap

CREATE TABLE IF NOT EXISTS graphs (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  config JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  graph_id TEXT REFERENCES graphs(id),
  status TEXT DEFAULT 'pending',
  started_at TIMESTAMPTZ DEFAULT NOW(),
  finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS observations (
  id TEXT PRIMARY KEY,
  run_id TEXT REFERENCES runs(id),
  source TEXT,
  content TEXT NOT NULL,
  url TEXT,
  confidence FLOAT DEFAULT 0.5,
  tags TEXT[] DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS event_nodes (
  id TEXT,
  run_id TEXT REFERENCES runs(id),
  graph_id TEXT,
  layer INT NOT NULL,
  label TEXT NOT NULL,
  probability FLOAT NOT NULL,
  formula_prob FLOAT,
  llm_delta FLOAT,
  reasoning TEXT,
  inputs JSONB DEFAULT '[]',
  observation_ids TEXT[] DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (id, run_id)
);

CREATE TABLE IF NOT EXISTS conclusions (
  id TEXT,
  run_id TEXT REFERENCES runs(id),
  graph_id TEXT,
  label TEXT NOT NULL,
  probability FLOAT NOT NULL,
  confidence_band JSONB,
  narrative TEXT,
  supporting_event_ids TEXT[] DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (id, run_id)
);

CREATE INDEX IF NOT EXISTS idx_runs_graph_id ON runs(graph_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_runs_graph_running
  ON runs(graph_id)
  WHERE status = 'running';
CREATE INDEX IF NOT EXISTS idx_observations_run_id ON observations(run_id);
CREATE INDEX IF NOT EXISTS idx_event_nodes_run_id_layer ON event_nodes(run_id, layer);
CREATE INDEX IF NOT EXISTS idx_conclusions_run_id ON conclusions(run_id);
