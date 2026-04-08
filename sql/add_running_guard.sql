-- One-time migration for existing projects:
-- 1) keep at most one running run per graph_id
-- 2) enforce it with a partial unique index

WITH ranked_running AS (
  SELECT
    id,
    ROW_NUMBER() OVER (PARTITION BY graph_id ORDER BY started_at DESC NULLS LAST, id DESC) AS rn
  FROM runs
  WHERE status = 'running'
)
UPDATE runs
SET
  status = 'failed',
  finished_at = COALESCE(finished_at, NOW())
WHERE id IN (
  SELECT id
  FROM ranked_running
  WHERE rn > 1
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_runs_graph_running
  ON runs(graph_id)
  WHERE status = 'running';
