-- The v2 change feed is driven by changed_at: clients poll
-- /v1/maps/targets/changes with a (changed_at, target_id) cursor and apply
-- only what moved since their last fetch.  The column must exist on every
-- write path before the feed can be trusted, so existing rows are backfilled
-- from the newest timestamp they already carry - a row that never changed
-- hands (reserved -> dispatching) looks as old as its last sighting, which is
-- exactly what a client that never saw it needs.
ALTER TABLE map_targets ADD COLUMN changed_at INTEGER NOT NULL DEFAULT 0;
UPDATE map_targets SET changed_at = MAX(last_seen_at, COALESCE(status_at, 0));
CREATE INDEX IF NOT EXISTS idx_map_targets_changed
    ON map_targets(server_key, map_kind, changed_at, target_id);
