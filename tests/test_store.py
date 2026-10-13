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
        assert version == 2
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
