CREATE TABLE locations (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE CHECK (name <> '' AND name = trim(name)),
    kind TEXT NOT NULL CHECK (kind IN ('shelf', 'box')),
    created_at TEXT NOT NULL
);
