"""The private catalog and job queue, shared by every app writer."""
import json
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


def _owned(db, job_id, owner):
    job = _get(db, "jobs", job_id)
    if job["status"] != "running" or job["owner"] != owner:
        raise Conflict("this worker no longer owns the running job")
    return job


def fail_job(db, job_id, owner, error, now=None):
    """Keep a failure visible and requeue it while attempts remain."""
    with _write(db):
        job = _owned(db, job_id, owner)
        status = "queued" if job["attempts"] < 3 else "failed"
        db.execute("UPDATE jobs SET status = ?, owner = NULL, error = ?, finished_at = ? WHERE id = ?",
                   (status, error, _stamp(now), job_id))
        return _get(db, "jobs", job_id)


def retry_job(db, job_id):
    """Restart a completed or failed job with a fresh retry allowance."""
    with _write(db):
        job = _get(db, "jobs", job_id)
        if job["status"] not in ("done", "failed"):
            raise Invalid("only a done or failed job can be retried")
        db.execute("""UPDATE jobs SET status = 'queued', attempts = 0, owner = NULL,
                      heartbeat_at = NULL, started_at = NULL, finished_at = NULL, error = NULL WHERE id = ?""",
                   (job_id,))
        return _get(db, "jobs", job_id)


def finish_job(db, job_id, owner, records, now=None):
    """Import a running owner's evidence and mark its job done in one transaction."""
    with _write(db):
        job = _owned(db, job_id, owner)
        if not isinstance(records, list):
            raise Invalid("records must be a list of row objects")
        stamp = _stamp(now)
        previous = db.execute("SELECT coalesce(max(attempt), 0) FROM observations WHERE capture_id = ?",
                              (job["capture_id"],)).fetchone()[0]
        # retry_job resets the retry budget, but imported evidence must keep distinct attempt numbers.
        attempt = max(job["attempts"], previous + 1)
        db.execute("UPDATE observations SET status = 'superseded' WHERE capture_id = ? AND status = 'open'",
                   (job["capture_id"],))
        for index, row in enumerate(records):
            if not isinstance(row, dict) or any(not isinstance(row.get(key, ""), str)
                                                for key in ("title", "read_status", "other_reading")):
                raise Invalid(f"record {index} must have text title, read_status and other_reading fields")
            try:
                encoded = json.dumps(row, ensure_ascii=False, allow_nan=False)
            except (TypeError, ValueError) as error:
                raise Invalid(f"record {index} must contain JSON values") from error
            db.execute("""INSERT INTO observations
                          (capture_id, attempt, row, read_status, title, other_reading, record, status, created_at)
                          VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?)""",
                       (job["capture_id"], attempt, index, row.get("read_status", ""),
                        row.get("title", ""), row.get("other_reading", ""), encoded, stamp))
        db.execute("UPDATE jobs SET status = 'done', owner = NULL, finished_at = ?, error = NULL WHERE id = ?",
                   (stamp, job_id))
        return _get(db, "jobs", job_id)


def observations(db, status="open", capture_id=None):
    """List evidence with its original record and capture for review."""
    _choice(status, ("open", "used", "dismissed", "superseded"), "observation status")
    parameters = [status]
    where = "status = ?"
    if capture_id is not None:
        _uuid(capture_id, "capture id")
        where += " AND capture_id = ?"
        parameters.append(capture_id)
    result = []
    for row in db.execute(f"SELECT * FROM observations WHERE {where} ORDER BY id", parameters):
        observation = dict(row)
        observation["record"] = json.loads(observation["record"])
        observation["capture"] = _get(db, "captures", observation["capture_id"])
        result.append(observation)
    return result


TEXT_FIELDS = ("title", "sort_key", "author", "illustrator", "publisher", "year", "language", "isbn",
               "series", "tags", "source", "source_id", "notes")
BOOK_FIELDS = (*TEXT_FIELDS, "age_from", "age_to", "state", "location_id", "cover_capture_id", "needs_review")


def _fields(fields):
    if not isinstance(fields, dict):
        raise Invalid("book fields must be an object")
    for field in fields:
        if field not in BOOK_FIELDS:
            raise Invalid(f"{field} is not an editable book field")


def _book_fields(db, fields):
    _fields(fields)
    result = dict.fromkeys(TEXT_FIELDS, "")
    result.update(age_from=None, age_to=None, state="Active", cover_capture_id=None, needs_review=False)
    result.update(fields)
    for key in TEXT_FIELDS:
        if not isinstance(result[key], str):
            raise Invalid(f"{key} must be text")
    result["title"] = _name(result["title"], "book title")
    if not result["sort_key"]:
        result["sort_key"] = result["title"]
    _choice(result["state"], STATES, "state")
    if result.get("location_id") is None:
        raise Invalid("a book must have a location_id")
    _get(db, "locations", result["location_id"])
    if result["cover_capture_id"] is not None:
        _uuid(result["cover_capture_id"], "cover capture id")
        _get(db, "captures", result["cover_capture_id"])
    for field in ("age_from", "age_to"):
        value = result[field]
        if value == "" or value is None:
            result[field] = None
        elif isinstance(value, str) and value.isdecimal():
            result[field] = int(value)
        elif type(value) is not int:
            raise Invalid(f"{field} must be an integer or empty")
    if type(result["needs_review"]) is not bool:
        raise Invalid("needs_review must be true or false")
    return result


def _insert_book(db, fields, by, stamp):
    values = _book_fields(db, fields)
    values.update(created_by=_name(by, "created by"), reviewed_by=by, created_at=stamp, updated_at=stamp)
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    id = db.execute(f"INSERT INTO books ({columns}) VALUES ({placeholders})", tuple(values.values())).lastrowid
    return book(db, id)


def add_book(db, fields, by, *, now=None):
    """Add a physical copy entered by a person, with its location and initial version."""
    with _write(db):
        return _insert_book(db, fields, by, _stamp(now))


def book(db, id):
    """Return a copy's catalog fields and editing version as plain data."""
    result = _get(db, "books", id)
    result["needs_review"] = bool(result["needs_review"])
    return result
