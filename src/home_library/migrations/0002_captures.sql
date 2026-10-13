CREATE TABLE captures (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('shelf', 'cover', 'barcode')),
    location_id INTEGER NOT NULL REFERENCES locations(id),
    default_state TEXT NOT NULL CHECK (default_state IN ('Active', 'Stored', 'Retired', 'Gone')),
    group_id TEXT,
    uploaded_by TEXT NOT NULL,
    original_name TEXT NOT NULL,
    media_type TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    bytes INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX captures_sha256 ON captures(sha256);
CREATE TABLE jobs (
    id INTEGER PRIMARY KEY,
    capture_id TEXT NOT NULL UNIQUE REFERENCES captures(id),
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'done', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    owner TEXT,
    heartbeat_at TEXT,
    started_at TEXT,
    finished_at TEXT,
    error TEXT
);
