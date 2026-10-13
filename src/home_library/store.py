"""The private catalog and job queue, shared by every app writer."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from importlib.resources import files
from uuid import UUID, uuid4

from home_library.workspace import refuse_inside_checkout


def open(data_root):
    """Open a private WAL database and apply each packaged migration once."""
    root = refuse_inside_checkout(data_root)
    root.mkdir(parents=True, exist_ok=True)
    for directory in ("captures", "work"):
        (root / directory).mkdir(exist_ok=True)
    db = sqlite3.connect(root / "catalog.db")
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA journal_mode = WAL")
        migrations = sorted(files("home_library.migrations").iterdir(), key=lambda path: path.name)
        for migration in migrations:
            if not migration.name.endswith(".sql"):
                continue
            version = int(migration.name.split("_", 1)[0])
            db.execute("BEGIN IMMEDIATE")
            if version > db.execute("PRAGMA user_version").fetchone()[0]:
                # executescript commits an existing transaction; execute complete statements instead.
                statement = ""
                for line in migration.read_text(encoding="utf-8").splitlines(keepends=True):
                    statement += line
                    if sqlite3.complete_statement(statement):
                        db.execute(statement)
                        statement = ""
                db.execute(f"PRAGMA user_version = {version}")
            db.commit()
    except BaseException:
        db.close()
        raise
    return db


class Invalid(ValueError):
    """A request breaks a catalog rule."""


class Conflict(ValueError):
    """Another writer has already changed the requested row."""


class NotFound(LookupError):
    """The requested catalog row does not exist."""


def _stamp(now=None):
    value = now() if callable(now) else now
    if value is None:
        value = datetime.now(timezone.utc)
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise Invalid("now must be an ISO 8601 time with a timezone") from error
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise Invalid("now must include a timezone")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _name(value, field):
    if not isinstance(value, str) or not value.strip():
        raise Invalid(f"{field} must not be empty")
    return value.strip()


def _choice(value, choices, field):
    if value not in choices:
        raise Invalid(f"{field} must be one of {', '.join(choices)}")
    return value


def _get(db, table, id):
    row = db.execute(f"SELECT * FROM {table} WHERE id = ?", (id,)).fetchone()
    if row is None:
        raise NotFound(f"{table}: {id} was not found")
    return dict(row)


def add_location(db, name, kind, *, now=None):
    """Add a shelf or box under a unique name."""
    name = _name(name, "location name")
    _choice(kind, ("shelf", "box"), "location kind")
    try:
        with db:
            id = db.execute("INSERT INTO locations (name, kind, created_at) VALUES (?, ?, ?)",
                            (name, kind, _stamp(now))).lastrowid
    except sqlite3.IntegrityError as error:
        raise Invalid("a location with that name already exists") from error
    return _get(db, "locations", id)


def rename_location(db, id, name):
    """Rename a location without changing which books belong to it."""
    name = _name(name, "location name")
    _get(db, "locations", id)
    try:
        with db:
            db.execute("UPDATE locations SET name = ? WHERE id = ?", (name, id))
    except sqlite3.IntegrityError as error:
        raise Invalid("a location with that name already exists") from error
    return _get(db, "locations", id)


def locations(db):
    """List locations by name."""
    return [dict(row) for row in db.execute("SELECT * FROM locations ORDER BY name")]


STATES = ("Active", "Stored", "Retired", "Gone")


@contextmanager
def _write(db):
    """Reserve the writer before checking rows so concurrent callers see settled data."""
    db.execute("BEGIN IMMEDIATE")
    try:
        yield
        db.commit()
    except BaseException:
        db.rollback()
        raise


def _uuid(value, field):
    try:
        canonical = str(UUID(value)) if isinstance(value, str) else None
    except ValueError:
        canonical = None
    if canonical is None or value != canonical:
        raise Invalid(f"{field} must be a canonical lowercase UUID")
    return value


def _receipt(db, id, created):
    capture = _get(db, "captures", id)
    job = dict(db.execute("SELECT * FROM jobs WHERE capture_id = ?", (id,)).fetchone())
    receipt = {"capture": capture, "job": job, "created": created}
    duplicates = [row[0] for row in db.execute(
        "SELECT id FROM captures WHERE sha256 = ? AND id <> ? ORDER BY created_at, id", (capture["sha256"], id))]
    if duplicates:
        receipt["duplicate_of"] = duplicates
    return receipt


def add_capture(db, id, kind, location_id, default_state, uploaded_by, original_name, media_type, sha256,
                bytes, group_id=None, *, now=None):
    """Record an uploaded photo and its job atomically; repeated uploads keep their receipt."""
    _uuid(id, "capture id")
    with _write(db):
        existing = db.execute("SELECT sha256 FROM captures WHERE id = ?", (id,)).fetchone()
        if existing:
            if existing[0] != sha256:
                raise Conflict("this capture id already has a different photo hash")
            return _receipt(db, id, False)
        _choice(kind, ("shelf", "cover", "barcode"), "capture kind")
        _choice(default_state, STATES, "state")
        if group_id is not None:
            _uuid(group_id, "group id")
        _get(db, "locations", location_id)
        db.execute("""INSERT INTO captures
                      (id, kind, location_id, default_state, uploaded_by, original_name, media_type,
                       sha256, bytes, group_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                   (id, kind, location_id, default_state, uploaded_by, original_name, media_type,
                    sha256, bytes, group_id, _stamp(now)))
        db.execute("INSERT INTO jobs (capture_id, status) VALUES (?, 'queued')", (id,))
        return _receipt(db, id, True)


def _claimed(db, id):
    job = _get(db, "jobs", id)
    job["capture"] = _get(db, "captures", job["capture_id"])
    job["location"] = _get(db, "locations", job["capture"]["location_id"])["name"]
    return job


def claim_job(db, now=None):
    """Lease the oldest eligible job, retiring workers that stopped three times."""
    stamp = _stamp(now)
    cutoff = (datetime.fromisoformat(stamp.replace("Z", "+00:00")) - timedelta(minutes=20)).isoformat()
    with _write(db):
        while True:
            row = db.execute("""SELECT jobs.* FROM jobs JOIN captures ON captures.id = jobs.capture_id
                                WHERE jobs.status = 'queued' OR
                                    (jobs.status = 'running' AND julianday(heartbeat_at) < julianday(?))
                                ORDER BY julianday(captures.created_at), jobs.id LIMIT 1""", (cutoff,)).fetchone()
            if row is None:
                return None
            if row["attempts"] >= 3:
                db.execute("""UPDATE jobs SET status = 'failed', owner = NULL, finished_at = ?,
                              error = 'the worker stopped responding 3 times' WHERE id = ?""", (stamp, row["id"]))
                continue
            db.execute("""UPDATE jobs SET status = 'running', attempts = attempts + 1, owner = ?,
                          heartbeat_at = ?, started_at = ?, finished_at = NULL WHERE id = ?""",
                       (str(uuid4()), stamp, stamp, row["id"]))
            return _claimed(db, row["id"])


def heartbeat(db, job_id, owner, now=None):
    """Refresh a lease only while the caller is still its running owner."""
    with _write(db):
        changed = db.execute("""UPDATE jobs SET heartbeat_at = ?
                                WHERE id = ? AND status = 'running' AND owner = ?""",
                             (_stamp(now), job_id, owner)).rowcount
        return changed == 1
