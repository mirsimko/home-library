"""The catalog store keeps private evidence separate from the family's books."""
from importlib.resources import files

import pytest

from home_library import store


def test_open_creates_private_directories_and_migrates_once(tmp_path):
    root = tmp_path / "private"
    with store.open(root) as db:
        assert (root / "catalog.db").is_file()
        assert (root / "captures").is_dir()
        assert (root / "work").is_dir()
        assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        version = db.execute("PRAGMA user_version").fetchone()[0]
        assert version == 3
        db.execute("INSERT INTO locations (name, kind, created_at) VALUES ('Box A', 'box', '2026-01-01T00:00:00Z')")
    with store.open(root) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == version
        assert db.execute("SELECT name FROM locations").fetchone()[0] == "Box A"
    assert files("home_library.migrations").joinpath("0001_catalog.sql").is_file()


@pytest.mark.parametrize("git_file", [False, True])
def test_open_refuses_a_checkout_before_creating_anything(tmp_path, git_file):
    repo = tmp_path / "repo"
    repo.mkdir()
    if git_file:
        (repo / ".git").write_text("gitdir: /elsewhere\n")
    else:
        (repo / ".git").mkdir()
    with pytest.raises(ValueError, match="git checkout"):
        store.open(repo / "private")
    assert not (repo / "private").exists()


@pytest.fixture
def db(tmp_path):
    connection = store.open(tmp_path / "private")
    yield connection
    connection.close()


def test_locations_are_trimmed_unique_named_places(db):
    shelf = store.add_location(db, "  Shelf A  ", "shelf", now="2026-01-02T03:04:05Z")
    box = store.add_location(db, "Box B", "box", now="2026-01-02T03:04:05Z")
    assert isinstance(shelf, dict)
    assert shelf == {"id": 1, "name": "Shelf A", "kind": "shelf", "created_at": "2026-01-02T03:04:05Z"}
    assert store.rename_location(db, box["id"], " Box C ")["name"] == "Box C"
    assert [r["name"] for r in store.locations(db)] == ["Box C", "Shelf A"]
    with pytest.raises(store.Invalid, match="already exists"):
        store.add_location(db, "Shelf A", "box")
    with pytest.raises(store.Invalid, match="already exists"):
        store.rename_location(db, box["id"], " Shelf A ")
    with pytest.raises(store.NotFound):
        store.rename_location(db, 999, "Absent")


@pytest.mark.parametrize("name,kind", [("", "shelf"), (" \t ", "box"), (None, "box"), ("X", "room")])
def test_invalid_locations_leave_no_row(db, name, kind):
    with pytest.raises(store.Invalid):
        store.add_location(db, name, kind)
    assert store.locations(db) == []


CAPTURE_ID = "10000000-0000-4000-8000-000000000001"
SECOND_ID = "10000000-0000-4000-8000-000000000002"
NOW = "2026-01-02T03:04:05Z"


def capture(db, id=CAPTURE_ID, **changes):
    if not store.locations(db):
        store.add_location(db, "Shelf A", "shelf", now=NOW)
    fields = dict(id=id, kind="shelf", location_id=1, default_state="Active", uploaded_by="parent",
                  original_name="generated.jpg", media_type="image/jpeg", sha256="a" * 64, bytes=120, now=NOW)
    fields.update(changes)
    return store.add_capture(db, **fields)


def test_a_capture_and_its_single_job_have_an_idempotent_receipt(db):
    receipt = capture(db)
    assert receipt["created"] is True
    assert isinstance(receipt["capture"], dict) and isinstance(receipt["job"], dict)
    assert receipt["capture"]["created_at"] == NOW
    assert receipt["job"]["capture_id"] == CAPTURE_ID
    assert (receipt["job"]["status"], receipt["job"]["attempts"]) == ("queued", 0)
    repeated = capture(db, uploaded_by="other", original_name="changed.jpg")
    assert repeated == {**receipt, "created": False}
    with pytest.raises(store.Conflict, match="different"):
        capture(db, sha256="b" * 64)
    duplicate = capture(db, SECOND_ID)
    assert duplicate["duplicate_of"] == [CAPTURE_ID]
    assert duplicate["created"] is True
    assert db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 2


@pytest.mark.parametrize("changes", [
    {"id": "../escape"}, {"id": CAPTURE_ID.upper().replace("10000000", "ABCDEF00")},
    {"id": CAPTURE_ID.replace("-", "")}, {"id": "{" + CAPTURE_ID + "}"}, {"id": " " + CAPTURE_ID},
    {"id": None}, {"kind": "portrait"}, {"default_state": "active"}, {"default_state": "Lost"},
    {"group_id": "../group"},
])
def test_capture_ids_kinds_states_and_group_ids_are_validated(db, changes):
    with pytest.raises(store.Invalid):
        capture(db, **changes)
    assert db.execute("SELECT count(*) FROM captures").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0


def test_a_capture_requires_an_existing_location(db):
    with pytest.raises(store.NotFound):
        capture(db, location_id=999)
    assert db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0


def test_claims_are_oldest_first_and_carry_capture_and_location(db):
    later = capture(db, now="2026-01-02T03:04:06Z")
    earlier = capture(db, SECOND_ID)
    statements = []
    db.set_trace_callback(statements.append)
    job = store.claim_job(db, NOW)
    db.set_trace_callback(None)
    assert "BEGIN IMMEDIATE" in statements
    assert job["id"] == earlier["job"]["id"]
    assert job["capture"] == earlier["capture"]
    assert job["location"] == "Shelf A"
    assert (job["status"], job["attempts"], job["heartbeat_at"], job["started_at"]) == ("running", 1, NOW, NOW)
    assert job["owner"]
    second = store.claim_job(db, NOW)
    assert second["id"] == later["job"]["id"]
    assert second["owner"] != job["owner"]
    assert store.claim_job(db, NOW) is None


def test_stale_jobs_are_reclaimed_only_after_twenty_minutes(db):
    capture(db)
    first = store.claim_job(db, NOW)
    assert store.claim_job(db, "2026-01-02T03:24:05Z") is None
    second = store.claim_job(db, "2026-01-02T03:24:06Z")
    assert second["id"] == first["id"]
    assert second["attempts"] == 2
    assert second["owner"] != first["owner"]
    assert not store.heartbeat(db, first["id"], first["owner"], "2026-01-02T03:30:00Z")
    assert store.heartbeat(db, second["id"], second["owner"], "2026-01-02T03:30:00Z")
    assert store.claim_job(db, "2026-01-02T03:49:59Z") is None
    third = store.claim_job(db, "2026-01-02T03:50:01Z")
    assert third["attempts"] == 3
    capture(db, SECOND_ID)
    next_job = store.claim_job(db, "2026-01-02T04:11:00Z")
    assert next_job["capture_id"] == SECOND_ID
    failed = capture(db)["job"]
    assert failed["status"] == "failed"
    assert failed["error"] == "the worker stopped responding 3 times"
    assert failed["finished_at"] == "2026-01-02T04:11:00Z"
    assert not store.heartbeat(db, failed["id"], third["owner"], "2026-01-02T04:12:00Z")


def test_failure_requeues_twice_then_stays_visible_until_retry(db):
    receipt = capture(db)
    for attempt in range(1, 4):
        job = store.claim_job(db, NOW)
        assert job["attempts"] == attempt
        failed = store.fail_job(db, job["id"], job["owner"], "invented failure", NOW)
        assert failed["status"] == ("queued" if attempt < 3 else "failed")
        assert failed["error"] == "invented failure"
        assert not store.heartbeat(db, job["id"], job["owner"], NOW)
    assert store.claim_job(db, NOW) is None
    retried = store.retry_job(db, receipt["job"]["id"])
    assert retried["status"] == "queued" and retried["attempts"] == 0
    assert retried["owner"] is None and retried["finished_at"] is None
    assert store.claim_job(db, NOW)["attempts"] == 1


def test_a_superseded_worker_cannot_fail_or_retry_a_running_job(db):
    capture(db)
    old = store.claim_job(db, NOW)
    current = store.claim_job(db, "2026-01-02T03:25:00Z")
    before = capture(db)["job"]
    with pytest.raises(store.Conflict):
        store.fail_job(db, old["id"], old["owner"], "late failure", NOW)
    assert capture(db)["job"] == before
    with pytest.raises(store.Invalid):
        store.retry_job(db, current["id"])
    assert capture(db)["job"] == before
    with pytest.raises(store.NotFound):
        store.fail_job(db, 999, "absent", "failure", NOW)
    with pytest.raises(store.NotFound):
        store.retry_job(db, 999)


RECORD_COLUMNS = (
    "title sort_key author illustrator publisher year language isbn series age_from age_to tags state location "
    "cover_photo source source_id needs_review notes photo read_status other_reading catalogue_title other_text "
    "where read_ids pick_verdict candidate_count").split()


def record(title="Měsíční člun", **changes):
    row = dict.fromkeys(RECORD_COLUMNS, "")
    row.update(title=title, sort_key=title, language="cs", read_status="agreed", needs_review=True,
               candidate_count=0, photo="generated.jpg", where="r1c1-r0.jpg, #1", read_ids="a; b")
    row.update(changes)
    return row


def finish(db, rows, id=CAPTURE_ID, **changes):
    receipt = capture(db, id, **changes)
    job = store.claim_job(db, NOW)
    assert job["id"] == receipt["job"]["id"]
    store.finish_job(db, job["id"], job["owner"], rows, NOW)
    return store.observations(db, capture_id=id)


def test_finishing_imports_whole_records_as_open_evidence_and_no_books(db):
    receipt = capture(db)
    job = store.claim_job(db, NOW)
    rows = [record(other_reading="Měsíční loď"), record("", read_status="unreadable")]
    done = store.finish_job(db, job["id"], job["owner"], rows, NOW)
    assert done["status"] == "done" and done["finished_at"] == NOW
    observations = store.observations(db)
    assert [r["record"] for r in observations] == rows
    assert [(r["attempt"], r["row"], r["status"]) for r in observations] == [(1, 0, "open"), (1, 1, "open")]
    assert observations[0]["capture"] == receipt["capture"]
    assert observations[0]["other_reading"] == "Měsíční loď"
    assert observations[0]["created_at"] == NOW
    assert store.observations(db, capture_id=SECOND_ID) == []
    assert db.execute("SELECT count(*) FROM books").fetchone()[0] == 0
    assert not store.heartbeat(db, job["id"], job["owner"], NOW)


def test_a_late_finish_changes_nothing(db):
    capture(db)
    old = store.claim_job(db, NOW)
    store.claim_job(db, "2026-01-02T03:25:00Z")
    before = capture(db)["job"]
    with pytest.raises(store.Conflict):
        store.finish_job(db, old["id"], old["owner"], [record()], NOW)
    assert capture(db)["job"] == before
    assert store.observations(db) == []


@pytest.mark.parametrize("rows", [{}, [None], [record(), {"title": 3}], [record(), {"title": "x", "notes": object()}]])
def test_a_bad_import_leaves_the_job_and_all_observations_unchanged(db, rows):
    capture(db)
    job = store.claim_job(db, NOW)
    before = capture(db)["job"]
    with pytest.raises(store.Invalid):
        store.finish_job(db, job["id"], job["owner"], rows, NOW)
    assert store.observations(db) == []
    assert capture(db)["job"] == before
