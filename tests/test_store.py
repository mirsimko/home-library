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
        assert version == 1
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
