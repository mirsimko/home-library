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
        assert version == 5
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


def test_reruns_keep_evidence_and_supersede_earlier_open_rows(db):
    (old,) = finish(db, [record()])
    store.retry_job(db, capture(db)["job"]["id"])
    job = store.claim_job(db, NOW)
    assert job["attempts"] == 1
    store.finish_job(db, job["id"], job["owner"], [record("Hvězdná bárka")], NOW)
    (new,) = store.observations(db)
    assert (new["attempt"], new["row"]) == (2, 0)
    assert new["title"] == "Hvězdná bárka"
    assert store.observations(db, "superseded")[0]["id"] == old["id"]
    store.retry_job(db, job["id"])
    third = store.claim_job(db, NOW)
    store.finish_job(db, third["id"], third["owner"], [], NOW)
    assert store.observations(db) == []
    assert len(store.observations(db, "superseded")) == 2


def typed_book(db, **changes):
    if not store.locations(db):
        store.add_location(db, "Shelf A", "shelf", now=NOW)
    return store.add_book(db, {"title": " Měsíční člun ", "location_id": 1, **changes}, "parent", now=NOW)


def test_a_book_typed_by_hand_is_a_plain_versioned_record(db):
    added = typed_book(db, author="Lenka Testová", age_from="3", age_to="8", tags="moon, boats")
    assert isinstance(added, dict)
    assert added["title"] == added["sort_key"] == "Měsíční člun"
    assert added["state"] == "Active"
    assert added["version"] == 1
    assert added["created_by"] == "parent"
    assert added["created_at"] == added["updated_at"] == NOW
    assert added["age_from"] == 3 and added["age_to"] == 8
    assert isinstance(added["needs_review"], bool)
    assert store.book(db, added["id"]) == added
    with pytest.raises(store.NotFound):
        store.book(db, 999)
    for state in ("Stored", "Retired", "Gone"):
        assert typed_book(db, state=state)["state"] == state


@pytest.mark.parametrize("changes", [
    {"title": " \n\t "}, {"title": None}, {"state": "lost"}, {"unknown": "x"}, {"version": 7},
    {"author": []}, {"age_from": "three"}, {"age_to": 2.5}, {"needs_review": "false"},
])
def test_invalid_book_fields_leave_no_book(db, changes):
    with pytest.raises(store.Invalid):
        typed_book(db, **changes)
    assert db.execute("SELECT count(*) FROM books").fetchone()[0] == 0


def test_books_require_a_location_and_a_cover_capture_when_given(db):
    with pytest.raises(store.NotFound):
        typed_book(db, location_id=999)
    with pytest.raises(store.Invalid, match="location"):
        store.add_book(db, {"title": "Hvězdná bárka"}, "parent", now=NOW)
    with pytest.raises(store.NotFound):
        typed_book(db, cover_capture_id=CAPTURE_ID)
    assert db.execute("SELECT count(*) FROM books").fetchone()[0] == 0


def test_edits_are_partial_versioned_and_attributed(db):
    original = typed_book(db, notes="keep this", age_from=3)
    changed = store.update_book(db, original["id"], 1, {"title": " Hvězdná bárka ", "state": "Gone"},
                                "editor", now="2026-01-03T00:00:00Z")
    assert changed["title"] == "Hvězdná bárka" and changed["state"] == "Gone"
    assert changed["notes"] == "keep this" and changed["age_from"] == 3
    assert changed["version"] == 2 and changed["reviewed_by"] == "editor"
    assert changed["created_by"] == "parent" and changed["created_at"] == NOW
    assert changed["updated_at"] == "2026-01-03T00:00:00Z"
    with pytest.raises(store.Conflict):
        store.update_book(db, original["id"], 1, {"notes": "stale overwrite"}, "other", now=NOW)
    assert store.book(db, original["id"]) == changed


@pytest.mark.parametrize("changes", [{"unknown": "x"}, {"created_by": "x"}, {"version": 9},
                                     {"title": " "}, {"state": "lost"}, {"location_id": None}])
def test_invalid_edits_leave_the_book_and_version_unchanged(db, changes):
    original = typed_book(db)
    with pytest.raises(store.Invalid):
        store.update_book(db, original["id"], 1, changes, "editor", now=NOW)
    assert store.book(db, original["id"]) == original


def test_editing_a_missing_book_or_moving_to_a_missing_location_is_refused(db):
    with pytest.raises(store.NotFound):
        store.update_book(db, 999, 1, {"title": "Hvězdná bárka"}, "editor", now=NOW)
    original = typed_book(db)
    with pytest.raises(store.NotFound):
        store.update_book(db, original["id"], 1, {"location_id": 999}, "editor", now=NOW)
    assert store.book(db, original["id"]) == original


def test_approval_combines_read_title_catalogue_fields_and_cover(db):
    (cover,) = finish(db, [record("Měsíční člun", author="read author")], kind="cover", default_state="Stored")
    (barcode,) = finish(db, [record("", read_status="barcode", catalogue_title="Different catalogue title",
                                   sort_key="Mesicni clun", author="Lenka Testová", publisher="Test Press",
                                   year="2020", isbn="9780000000002", series="Invented voyages", source="test",
                                   source_id="42", age_from="3", age_to="")], SECOND_ID, kind="barcode")
    original_records = [cover["record"], barcode["record"]]
    book = store.approve(db, [cover["id"], barcode["id"]], {}, "reviewer", now=NOW)
    assert book["title"] == "Měsíční člun"
    assert book["sort_key"] == "Mesicni clun" and book["author"] == "Lenka Testová"
    assert (book["publisher"], book["year"], book["isbn"], book["series"]) == (
        "Test Press", "2020", "9780000000002", "Invented voyages")
    assert (book["source"], book["source_id"], book["age_from"], book["age_to"]) == ("test", "42", 3, None)
    assert book["language"] == "cs" and book["location_id"] == 1 and book["state"] == "Stored"
    assert book["cover_capture_id"] == CAPTURE_ID
    assert book["needs_review"] is False and book["reviewed_by"] == "reviewer"
    assert book["created_by"] == "reviewer" and book["created_at"] == book["updated_at"] == NOW
    assert store.observations(db) == []
    used = store.observations(db, "used")
    assert [r["record"] for r in used] == original_records
    assert [r["book_id"] for r in used] == [book["id"], book["id"]]


def test_approval_uses_given_fields_and_the_first_nonempty_read_title(db):
    rows = finish(db, [record("", read_status="unreadable"), record()])
    box = store.add_location(db, "Box B", "box", now=NOW)
    added = store.approve(db, [r["id"] for r in rows], {"title": "Hvězdná bárka", "author": "Typed Author",
                         "location_id": box["id"], "state": "Gone", "needs_review": True}, "reviewer", now=NOW)
    assert (added["title"], added["author"], added["location_id"], added["state"], added["needs_review"]) == (
        "Hvězdná bárka", "Typed Author", box["id"], "Gone", False)
    store.retry_job(db, capture(db)["job"]["id"])
    rows = finish(db, [record("", read_status="unreadable"), record("The Glass Canoe")])
    assert store.approve(db, [r["id"] for r in rows], {}, "reviewer", now=NOW)["title"] == "The Glass Canoe"


def test_approval_requires_nonempty_open_observations_and_is_atomic(db):
    rows = finish(db, [record(), record("The Glass Canoe")])
    for ids, fields, error in [([], {}, store.Invalid), ([rows[0]["id"], 999], {}, store.NotFound),
                               ([rows[0]["id"]], {"unknown": 1}, store.Invalid),
                               ([rows[0]["id"]], {"title": " "}, store.Invalid)]:
        with pytest.raises(error):
            store.approve(db, ids, fields, "reviewer", now=NOW)
        assert store.observations(db) == rows
        assert db.execute("SELECT count(*) FROM books").fetchone()[0] == 0
    store.approve(db, [rows[0]["id"]], {}, "reviewer", now=NOW)
    with pytest.raises(store.Invalid, match="open"):
        store.approve(db, [rows[1]["id"], rows[0]["id"]], {}, "reviewer", now=NOW)
    assert [r["id"] for r in store.observations(db)] == [rows[1]["id"]]
    assert db.execute("SELECT count(*) FROM books").fetchone()[0] == 1


def test_attach_sets_only_a_missing_cover_and_preserves_personal_edits(db):
    original = typed_book(db, title="The Glass Canoe", notes="person's note", author="Typed Author")
    (cover,) = finish(db, [record("different title")], kind="cover")
    attached = store.attach(db, [cover["id"]], original["id"], "reviewer", now="2026-01-03T00:00:00Z")
    assert attached["cover_capture_id"] == CAPTURE_ID
    assert (attached["title"], attached["notes"], attached["author"]) == (
        "The Glass Canoe", "person's note", "Typed Author")
    assert attached["version"] == 2 and attached["updated_at"] == "2026-01-03T00:00:00Z"
    assert store.observations(db, "used")[0]["book_id"] == original["id"]
    (another,) = finish(db, [record()], SECOND_ID, kind="cover")
    assert store.attach(db, [another["id"]], original["id"], "reviewer", now=NOW) == attached
    with pytest.raises(store.Invalid, match="open"):
        store.attach(db, [another["id"]], original["id"], "reviewer", now=NOW)


def test_dismiss_and_attach_validate_the_whole_selection(db):
    rows = finish(db, [record(), record("The Glass Canoe"), record("Hvězdná bárka")])
    original = typed_book(db)
    for action in (lambda ids: store.dismiss(db, ids, "reviewer"),
                   lambda ids: store.attach(db, ids, original["id"], "reviewer", now=NOW)):
        with pytest.raises(store.NotFound):
            action([rows[0]["id"], 999])
        assert store.observations(db) == rows
    dismissed = store.dismiss(db, [rows[0]["id"], rows[1]["id"]], "reviewer")
    assert [r["status"] for r in dismissed] == ["dismissed", "dismissed"]
    assert [r["id"] for r in store.observations(db, "dismissed")] == [rows[0]["id"], rows[1]["id"]]
    with pytest.raises(store.Invalid, match="open"):
        store.approve(db, [rows[0]["id"]], {}, "reviewer", now=NOW)
    with pytest.raises(store.Invalid, match="open"):
        store.attach(db, [rows[2]["id"], rows[0]["id"]], original["id"], "reviewer", now=NOW)
    with pytest.raises(store.NotFound):
        store.attach(db, [rows[2]["id"]], 999, "reviewer", now=NOW)
    assert [r["id"] for r in store.observations(db)] == [rows[2]["id"]]
    assert store.book(db, original["id"]) == original


def test_a_rerun_never_changes_used_dismissed_or_edited_books(db):
    rows = finish(db, [record(), record("The Glass Canoe"), record("Hvězdná bárka")])
    approved = store.approve(db, [rows[0]["id"]], {}, "reviewer", now=NOW)
    edited = store.update_book(db, approved["id"], 1, {"title": "Personal title", "notes": "Keep my edit"},
                               "editor", now=NOW)
    store.dismiss(db, [rows[1]["id"]], "reviewer")
    used = store.observations(db, "used")
    dismissed = store.observations(db, "dismissed")
    store.retry_job(db, capture(db)["job"]["id"])
    finish(db, [record("Machine's new guess")])
    assert store.book(db, edited["id"]) == edited
    assert store.observations(db, "used") == used
    assert store.observations(db, "dismissed") == dismissed
    assert [r["id"] for r in store.observations(db, "superseded")] == [rows[2]["id"]]


def test_books_move_together_and_each_editing_version_advances(db):
    first = typed_book(db)
    second = typed_book(db, title="The Glass Canoe")
    box = store.add_location(db, "Box B", "box", now=NOW)
    moved = store.move_books(db, [second["id"], first["id"]], box["id"], "Stored", by="mover", now=NOW)
    assert [r["id"] for r in moved] == [second["id"], first["id"]]
    for book in moved:
        assert (book["location_id"], book["state"], book["version"], book["reviewed_by"]) == (
            box["id"], "Stored", 2, "mover")
    gone = store.move_books(db, [first["id"]], state="Gone", by="mover", now=NOW)[0]
    assert gone["location_id"] == box["id"] and gone["version"] == 3
    relocated = store.move_books(db, [second["id"]], location_id=1, by="mover", now=NOW)[0]
    assert relocated["state"] == "Stored" and relocated["location_id"] == 1


def test_an_invalid_batch_move_changes_no_book(db):
    original = typed_book(db)
    for ids, changes, error in [([original["id"], 999], {"state": "Stored"}, store.NotFound),
                               ([original["id"]], {"location_id": 999}, store.NotFound),
                               ([original["id"]], {"state": "lost"}, store.Invalid),
                               ([original["id"]], {}, store.Invalid), ([], {"state": "Gone"}, store.Invalid)]:
        with pytest.raises(error):
            store.move_books(db, ids, **changes, by="mover", now=NOW)
        assert store.book(db, original["id"]) == original


def test_search_uses_trigrams_and_short_japanese_queries(db):
    czech = typed_book(db, title="Měsíční člun", sort_key="a")
    japanese = typed_book(db, title="ぐぽ", sort_key="b")
    author = typed_book(db, title="The Glass Canoe", sort_key="c", author="Invented Author", series="Silver boats")
    statements = []
    db.set_trace_callback(statements.append)
    assert store.search_books(db, "ěsí") == [czech]
    assert any("books_fts" in sql and "MATCH" in sql for sql in statements)
    assert db.execute("SELECT sql FROM sqlite_master WHERE name = 'books_fts'").fetchone()[0].find("trigram") >= 0
    statements.clear()
    assert store.search_books(db, "ぐぽ") == [japanese]
    assert any("LIKE" in sql for sql in statements)
    assert not any("MATCH" in sql for sql in statements)
    db.set_trace_callback(None)
    assert store.search_books(db, "ěs") == [czech]
    assert store.search_books(db, "Author") == [author]
    assert store.search_books(db, "boats") == [author]
    assert store.search_books(db, "missing") == []
    assert store.search_books(db, "a") == [czech, author]


def test_search_filters_tags_state_location_and_pages_in_catalog_order(db):
    store.add_location(db, "Shelf A", "shelf", now=NOW)
    box = store.add_location(db, "Box B", "box", now=NOW)
    first = typed_book(db, title="Alpha invented", sort_key="a", tags="moon, boats", state="Stored")
    second = typed_book(db, title="Beta invented", sort_key="a", tags="moonlight", location_id=box["id"])
    third = typed_book(db, title="Gamma invented", sort_key="c", tags="moon", location_id=box["id"], state="Gone")
    assert store.search_books(db) == [first, second, third]
    assert store.search_books(db, tag="moon") == [first, third]
    assert store.search_books(db, state="Stored", tag="moon", location_id=1) == [first]
    assert store.search_books(db, location_id=box["id"]) == [second, third]
    assert store.search_books(db, "invented", state="Gone", tag="moon") == [third]
    assert store.search_books(db, limit=1, offset=1) == [second]


def test_fts_tracks_updates_and_deletes_of_all_its_columns(db):
    original = typed_book(db, title="First vessel", sort_key="first key", author="First writer",
                          series="First series", isbn="111111")
    changed = store.update_book(db, original["id"], 1, {"title": "Second vessel", "sort_key": "second key",
                                "author": "Second writer", "series": "Second series", "isbn": "222222"},
                                "editor", now=NOW)
    for query in ("First", "111111"):
        assert store.search_books(db, query) == []
    for query in ("Second vessel", "second key", "Second writer", "Second series", "222222"):
        assert store.search_books(db, query) == [changed]
    # There is no public delete function; exercise the specified database trigger directly.
    with db:
        db.execute("DELETE FROM books WHERE id = ?", (original["id"],))
    assert store.search_books(db, "Second") == []
    assert db.execute("SELECT rowid FROM books_fts WHERE books_fts MATCH 'Second'").fetchall() == []
