PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS presence (
    server_key TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    last_seen_at INTEGER NOT NULL,
    PRIMARY KEY (server_key, actor_id)
);
CREATE INDEX IF NOT EXISTS idx_presence_server_seen
    ON presence(server_key, last_seen_at);

CREATE TABLE IF NOT EXISTS server_catalog (
    platform_key TEXT NOT NULL,
    server_key TEXT NOT NULL,
    area_id TEXT NOT NULL DEFAULT '',
    area_name TEXT NOT NULL DEFAULT '',
    game_http TEXT NOT NULL DEFAULT '',
    first_seen_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL,
    observation_count INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (platform_key, server_key)
);
CREATE INDEX IF NOT EXISTS idx_server_catalog_seen
    ON server_catalog(platform_key, last_seen_at DESC);

CREATE TABLE IF NOT EXISTS map_regions (
    server_key TEXT NOT NULL,
    map_kind TEXT NOT NULL,
    scan_x INTEGER NOT NULL,
    scan_y INTEGER NOT NULL,
    scanned_at INTEGER NOT NULL,
    observer_id TEXT NOT NULL,
    CHECK (map_kind IN ('bandit', 'mine')),
    PRIMARY KEY (server_key, map_kind, scan_x, scan_y)
);
CREATE INDEX IF NOT EXISTS idx_map_regions_fresh
    ON map_regions(server_key, map_kind, scanned_at);

CREATE TABLE IF NOT EXISTS map_targets (
    server_key TEXT NOT NULL,
    map_kind TEXT NOT NULL,
    target_id TEXT NOT NULL,
    x INTEGER NOT NULL,
    y INTEGER NOT NULL,
    target_type TEXT NOT NULL DEFAULT '',
    level INTEGER,
    data_json TEXT NOT NULL,
    last_seen_at INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'available',
    reserved_by TEXT NOT NULL DEFAULT '',
    reservation_token TEXT NOT NULL DEFAULT '',
    lease_until INTEGER NOT NULL DEFAULT 0,
    retry_after INTEGER NOT NULL DEFAULT 0,
    status_reason TEXT NOT NULL DEFAULT '',
    status_at INTEGER NOT NULL DEFAULT 0,
    CHECK (map_kind IN ('bandit', 'mine')),
    CHECK (status IN (
        'available', 'reserved', 'dispatching', 'dispatched',
        'rejected', 'missing', 'uncertain'
    )),
    PRIMARY KEY (server_key, map_kind, target_id)
);
CREATE INDEX IF NOT EXISTS idx_map_targets_available
    ON map_targets(server_key, map_kind, status, last_seen_at);
CREATE INDEX IF NOT EXISTS idx_map_targets_xy
    ON map_targets(server_key, map_kind, x, y);

CREATE TABLE IF NOT EXISTS map_target_regions (
    server_key TEXT NOT NULL,
    map_kind TEXT NOT NULL,
    target_id TEXT NOT NULL,
    scan_x INTEGER NOT NULL,
    scan_y INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL,
    CHECK (map_kind IN ('bandit', 'mine')),
    PRIMARY KEY (server_key, map_kind, target_id, scan_x, scan_y),
    FOREIGN KEY (server_key, map_kind, target_id)
        REFERENCES map_targets(server_key, map_kind, target_id)
        ON DELETE CASCADE,
    FOREIGN KEY (server_key, map_kind, scan_x, scan_y)
        REFERENCES map_regions(server_key, map_kind, scan_x, scan_y)
        ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_map_target_regions_scan
    ON map_target_regions(server_key, map_kind, scan_x, scan_y);

CREATE TABLE IF NOT EXISTS map_scan_leases (
    server_key TEXT NOT NULL,
    map_kind TEXT NOT NULL,
    scan_x INTEGER NOT NULL,
    scan_y INTEGER NOT NULL,
    owner TEXT NOT NULL,
    lease_token TEXT NOT NULL,
    lease_until INTEGER NOT NULL,
    CHECK (map_kind IN ('bandit', 'mine')),
    PRIMARY KEY (server_key, map_kind, scan_x, scan_y)
);
CREATE INDEX IF NOT EXISTS idx_map_scan_leases_expiry
    ON map_scan_leases(lease_until);
