-- The public directory is a complete platform snapshot.  It is intentionally
-- separate from server_catalog, which records only runtime observations made
-- by heartbeats.  Keeping the two meanings separate lets the administrator
-- list unopened/offline servers without pretending they are online.
CREATE TABLE IF NOT EXISTS server_directory (
    platform_key TEXT NOT NULL,
    server_key TEXT NOT NULL,
    area_id TEXT NOT NULL DEFAULT '',
    area_name TEXT NOT NULL DEFAULT '',
    target TEXT NOT NULL DEFAULT '',
    game_http TEXT NOT NULL DEFAULT '',
    first_seen_at INTEGER NOT NULL,
    last_directory_sync_at INTEGER NOT NULL,
    sync_count INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (platform_key, server_key)
);
CREATE INDEX IF NOT EXISTS idx_server_directory_name
    ON server_directory(platform_key, area_name, server_key);
CREATE INDEX IF NOT EXISTS idx_server_directory_sync
    ON server_directory(last_directory_sync_at DESC);

-- Existing heartbeat observations are also public directory facts.  Copy them
-- once so upgrading does not make already-known servers disappear from the
-- catalogue before the next client directory sync.
INSERT OR IGNORE INTO server_directory(
    platform_key,server_key,area_id,area_name,game_http,
    first_seen_at,last_directory_sync_at,sync_count
)
SELECT platform_key,server_key,area_id,area_name,game_http,
       first_seen_at,last_seen_at,1
FROM server_catalog;
