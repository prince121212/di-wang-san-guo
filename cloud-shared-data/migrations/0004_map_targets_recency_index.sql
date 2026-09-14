-- 刷黄/打矿 asks one question of this table: "the most recently seen targets
-- of this map on this server that I may take".  The old index led with status
--
--     idx_map_targets_available(server_key, map_kind, status, last_seen_at)
--
-- so last_seen_at was only ordered *within* a status.  The query spans three
-- statuses at once (available, plus reserved/rejected whose lease has run out),
-- which means the index could not produce the rows in recency order and SQLite
-- had to collect every target of that server and sort: 3,317 rows read to
-- return 481, 620,293 rows in two hours - 22% of the whole account's D1 reads.
--
-- Leading with last_seen_at lets the same query walk the range backwards and
-- stop at LIMIT.  status stays out of the key on purpose: it is checked per row
-- against a clock (lease_until/retry_after), so it can never drive a seek, and
-- keeping map_targets at two indexes keeps writes - the scarcer quota here -
-- exactly where they were.
DROP INDEX IF EXISTS idx_map_targets_available;

CREATE INDEX IF NOT EXISTS idx_map_targets_recent
    ON map_targets(server_key, map_kind, last_seen_at DESC);

-- An observation asks map_target_regions "which targets did this region hold",
-- and the answer it needs is the target_id.  The old key stopped at the
-- coordinates, so reading target_id meant going back to the table - and SQLite
-- would rather constrain two columns on the covering primary-key index than
-- four on this one and pay that lookup.  The result was a seek that still
-- walked every link the server had, once per region in the payload.  Carrying
-- target_id makes this index both fully constrained and covering, so the seek
-- lands on exactly the region asked about.  Same columns as the primary key,
-- ordered for the opposite question.
DROP INDEX IF EXISTS idx_map_target_regions_scan;

CREATE INDEX IF NOT EXISTS idx_map_target_regions_scan
    ON map_target_regions(server_key, map_kind, scan_x, scan_y, target_id);
