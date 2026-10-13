"""The private catalog and job queue, shared by every app writer."""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from importlib.resources import files
from pathlib import Path
from uuid import UUID, uuid4

from home_library.workspace import refuse_inside_checkout


def open(data_root=None):
    """Open a private WAL database and apply each packaged migration once."""
    if data_root is None:
        data_root = os.environ.get("HL_DATA") or Path.home() / "home-library"
    root = refuse_inside_checkout(data_root)
    for child in ("captures", "work", "catalog.db", "catalog.db-wal", "catalog.db-shm"):
        refuse_inside_checkout(root / child)
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
                for character in migration.read_text(encoding="utf-8"):
                    statement += character
                    if character == ";" and sqlite3.complete_statement(statement):
                        db.execute(statement)
                        statement = ""
                if statement.strip():
                    db.execute(statement)
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
    if table == "captures":
        _uuid(id, "capture id")
    elif type(id) is not int:
        raise Invalid(f"{table} id must be an integer")
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


def validate_capture(db, id, kind, location_id, default_state, uploaded_by, original_name, media_type,
                     sha256, bytes, group_id=None):
    """Check upload metadata before publishing its file, without changing the store."""
    _uuid(id, "capture id")
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
    if not isinstance(sha256, str) or len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256):
        raise Invalid("sha256 must be 64 lowercase hexadecimal characters")
    if type(bytes) is not int or bytes < 0:
        raise Invalid("bytes must be a non-negative integer")
    _choice(media_type, ("image/jpeg", "image/png", "image/webp"), "media type")
    _name(uploaded_by, "uploaded by")
    if not isinstance(original_name, str):
        raise Invalid("original_name must be text")


def add_capture(db, id, kind, location_id, default_state, uploaded_by, original_name, media_type, sha256,
                bytes, group_id=None, *, now=None):
    """Record an uploaded photo and its job atomically; repeated uploads keep their receipt."""
    _uuid(id, "capture id")
    with _write(db):
        existing = validate_capture(db, id, kind, location_id, default_state, uploaded_by,
                                    original_name, media_type, sha256, bytes, group_id)
        if existing is not None:
            return existing
        uploaded_by = _name(uploaded_by, "uploaded by")
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
    cutoff = datetime.fromisoformat(stamp.replace("Z", "+00:00")) - timedelta(minutes=20)
    with _write(db):
        candidates = db.execute("""SELECT jobs.*, captures.created_at AS uploaded_at FROM jobs
                                   JOIN captures ON captures.id = jobs.capture_id
                                   WHERE jobs.status IN ('queued', 'running')""").fetchall()
        # SQLite's date functions round to milliseconds; lease boundaries need the full saved precision.
        candidates.sort(key=lambda row: (datetime.fromisoformat(row["uploaded_at"].replace("Z", "+00:00")),
                                         row["id"]))
        for row in candidates:
            if row["status"] == "running" and row["heartbeat_at"] is not None:
                heartbeat_at = datetime.fromisoformat(row["heartbeat_at"].replace("Z", "+00:00"))
                if heartbeat_at >= cutoff:
                    continue
            if row["attempts"] >= 3:
                db.execute("""UPDATE jobs SET status = 'failed', owner = NULL, finished_at = ?,
                              error = 'the worker stopped responding 3 times' WHERE id = ?""", (stamp, row["id"]))
                continue
            db.execute("""UPDATE jobs SET status = 'running', attempts = attempts + 1, owner = ?,
                          heartbeat_at = ?, started_at = ?, finished_at = NULL WHERE id = ?""",
                       (str(uuid4()), stamp, stamp, row["id"]))
            return _claimed(db, row["id"])
        return None


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
    result["tags"] = ", ".join(tag.strip() for tag in result["tags"].split(",") if tag.strip())
    if not result["sort_key"]:
        result["sort_key"] = result["title"]
    _choice(result["state"], STATES, "state")
    if result.get("location_id") is None:
        raise Invalid("a book must have an integer location_id")
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


def _update_book(db, original, changes, by, stamp):
    _fields(changes)
    fields = {key: original[key] for key in BOOK_FIELDS}
    fields.update(changes)
    values = _book_fields(db, fields)
    values.update(version=original["version"] + 1, reviewed_by=_name(by, "reviewed by"), updated_at=stamp)
    assignments = ", ".join(f"{key} = ?" for key in values)
    db.execute(f"UPDATE books SET {assignments} WHERE id = ?", (*values.values(), original["id"]))
    return book(db, original["id"])


def update_book(db, id, version, changes, by, *, now=None):
    """Apply a partial edit only to the version the person actually saw."""
    if type(version) is not int:
        raise Invalid("version must be an integer")
    with _write(db):
        original = book(db, id)
        if original["version"] != version:
            raise Conflict("this book has changed; read its current version before editing")
        return _update_book(db, original, changes, by, _stamp(now))


def _ids(ids):
    if not isinstance(ids, (list, tuple)) or not ids or any(type(id) is not int or id < 1 for id in ids):
        raise Invalid("choose at least one row by its integer id")
    return list(dict.fromkeys(ids))


def _open_observations(db, ids):
    result = []
    for id in _ids(ids):
        observation = _get(db, "observations", id)
        if observation["status"] != "open":
            raise Invalid(f"observation {id} is not open")
        observation["record"] = json.loads(observation["record"])
        observation["capture"] = _get(db, "captures", observation["capture_id"])
        result.append(observation)
    return result


def _cover(observations):
    return next((o["capture_id"] for o in observations if o["capture"]["kind"] == "cover"), None)


def _use(db, observations, book_id):
    for observation in observations:
        db.execute("UPDATE observations SET status = 'used', book_id = ? WHERE id = ?",
                   (book_id, observation["id"]))


def approve(db, observation_ids, fields, by, *, now=None):
    """Create one reviewed physical copy from evidence chosen by a person."""
    with _write(db):
        _fields(fields)
        evidence = _open_observations(db, observation_ids)
        records = [observation["record"] for observation in evidence]
        inherited = {}
        for key in (*TEXT_FIELDS, "age_from", "age_to"):
            inherited[key] = next((row[key] for row in records if row.get(key) not in (None, "")), "")
        inherited["title"] = next((row["title"] for row in records
                                   if isinstance(row.get("title"), str) and row["title"].strip()), "")
        catalogue = next((row for row in records if row.get("source") or row.get("catalogue_title")), None)
        if catalogue is not None:
            for key in ("sort_key", "author", "publisher", "year", "isbn", "series", "source", "source_id",
                        "age_from", "age_to"):
                inherited[key] = catalogue.get(key, "")
        inherited.update(location_id=evidence[0]["capture"]["location_id"],
                         state=evidence[0]["capture"]["default_state"], cover_capture_id=_cover(evidence))
        inherited.update(fields)
        inherited["needs_review"] = False
        result = _insert_book(db, inherited, by, _stamp(now))
        _use(db, evidence, result["id"])
        return result


def attach(db, observation_ids, book_id, by, *, now=None):
    """Use evidence for an existing copy, filling its cover only when it has none."""
    with _write(db):
        _name(by, "reviewed by")
        evidence = _open_observations(db, observation_ids)
        result = book(db, book_id)
        cover = _cover(evidence)
        if result["cover_capture_id"] is None and cover is not None:
            result = _update_book(db, result, {"cover_capture_id": cover}, by, _stamp(now))
        _use(db, evidence, book_id)
        return result


def dismiss(db, observation_ids, by):
    """Keep unwanted open evidence visible as dismissed without making a book."""
    with _write(db):
        _name(by, "dismissed by")
        evidence = _open_observations(db, observation_ids)
        for observation in evidence:
            db.execute("UPDATE observations SET status = 'dismissed' WHERE id = ?", (observation["id"],))
            observation["status"] = "dismissed"
        return evidence


def move_books(db, ids, location_id=None, state=None, *, by, now=None):
    """Move selected copies or change their state, with no partial batch on failure."""
    changes = {}
    if location_id is not None:
        changes["location_id"] = location_id
    if state is not None:
        changes["state"] = state
    if not changes:
        raise Invalid("choose a location or state for the books")
    with _write(db):
        originals = [book(db, id) for id in _ids(ids)]
        stamp = _stamp(now)
        return [_update_book(db, original, changes, by, stamp) for original in originals]


def search_books(db, query="", state=None, location_id=None, tag=None, limit=50, offset=0):
    """Find copies by catalog text, using LIKE for titles shorter than a trigram."""
    if not isinstance(query, str):
        raise Invalid("query must be text")
    if state is not None:
        _choice(state, STATES, "state")
    if tag is not None and not isinstance(tag, str):
        raise Invalid("tag must be text")
    if type(limit) is not int or limit < 0 or type(offset) is not int or offset < 0:
        raise Invalid("limit and offset must be non-negative integers")
    clauses = []
    parameters = []
    if query:
        if len(query) >= 3:
            clauses.append("id IN (SELECT rowid FROM books_fts WHERE books_fts MATCH ?)")
            parameters.append('"' + query.replace('"', '""') + '"')
        else:
            clauses.append("(" + " OR ".join(f"{key} LIKE ? ESCAPE '\\'" for key in
                                             ("title", "sort_key", "author", "series", "isbn")) + ")")
            pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            parameters.extend([pattern] * 5)
    if state is not None:
        clauses.append("state = ?")
        parameters.append(state)
    if location_id is not None:
        clauses.append("location_id = ?")
        parameters.append(location_id)
    if tag is not None:
        clauses.append("instr(',' || replace(tags, ', ', ',') || ',', ',' || ? || ',') > 0")
        parameters.append(tag)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    rows = db.execute(f"SELECT * FROM books{where} ORDER BY sort_key, title, id LIMIT ? OFFSET ?",
                      (*parameters, limit, offset))
    return [{**dict(row), "needs_review": bool(row["needs_review"])} for row in rows]


def export_rows(db):
    """Export catalog fields in spec 2.1 order, with portable relative cover paths."""
    return _export_rows(db, False)


def _export_rows(db, include_captures):
    """Read catalogue fields and evidence together so each export has one SQLite snapshot."""
    result = []
    for row in db.execute("""SELECT books.*, locations.name AS location, captures.media_type AS cover_media,
                             (SELECT group_concat(DISTINCT capture_id) FROM observations
                              WHERE book_id = books.id) AS evidence_ids
                             FROM books JOIN locations ON locations.id = books.location_id
                             LEFT JOIN captures ON captures.id = books.cover_capture_id
                             ORDER BY sort_key, title, books.id"""):
        exported = {key: row[key] for key in TEXT_FIELDS[:9]}
        exported.update(age_from=row["age_from"], age_to=row["age_to"], tags=row["tags"], state=row["state"],
                        location=row["location"])
        cover = ""
        if row["cover_capture_id"]:
            extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[row["cover_media"]]
            cover = f"captures/{row['cover_capture_id']}.{extension}"
        exported.update(cover_photo=cover, source=row["source"], source_id=row["source_id"],
                        needs_review=bool(row["needs_review"]), notes=row["notes"])
        if include_captures:
            ids = set(row["evidence_ids"].split(",")) if row["evidence_ids"] else set()
            if row["cover_capture_id"] is not None:
                ids.add(row["cover_capture_id"])
            exported["capture_ids"] = sorted(ids)
        result.append(exported)
    return result


def capture(db, id):
    """Read a stored receipt with the number of observations still open."""
    result = _receipt(db, id, False)
    result["open_observations"] = db.execute(
        "SELECT count(*) FROM observations WHERE capture_id = ? AND status = 'open'", (id,)).fetchone()[0]
    return result


def captures(db, ids=None):
    """List recent receipts, optionally restricted to client capture ids."""
    if ids is not None:
        for id in ids:
            _uuid(id, "capture id")
    rows = list(db.execute("SELECT id, created_at FROM captures"))
    rows.sort(key=lambda row: (datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")), row["id"]),
              reverse=True)
    return [capture(db, row["id"]) for row in rows if ids is None or row["id"] in ids]


def jobs(db):
    """List jobs in queue order with their saved heartbeats."""
    return [dict(row) for row in db.execute("SELECT * FROM jobs ORDER BY id")]


def health(db):
    """Summarise worker activity without exposing any catalogue text."""
    queue = jobs(db)
    seen = [job["heartbeat_at"] for job in queue if job["heartbeat_at"] is not None]
    latest = max(seen, key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00"))) if seen else None
    return {"ok": True, "worker_seen": latest, "queued": sum(job["status"] == "queued" for job in queue),
            "failed": sum(job["status"] == "failed" for job in queue)}


def observation(db, id):
    """Read one observation, including its original record and capture."""
    result = _get(db, "observations", id)
    result["record"] = json.loads(result["record"])
    result["capture"] = _get(db, "captures", result["capture_id"])
    return result


def export_books(db):
    """Add all evidence and cover capture ids to the portable catalogue export."""
    return _export_rows(db, True)
