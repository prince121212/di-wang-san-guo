CREATE TABLE IF NOT EXISTS admin_login_attempts (
    client_key TEXT PRIMARY KEY,
    failure_count INTEGER NOT NULL DEFAULT 0,
    first_failure_at INTEGER NOT NULL,
    locked_until INTEGER NOT NULL DEFAULT 0,
    last_attempt_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_admin_login_attempts_last
    ON admin_login_attempts(last_attempt_at);
