"""The catalog store keeps private evidence separate from books."""
from importlib.resources import files

import pytest
from store_helpers import (
    NOW,
    migration_directory,
)
from store_helpers import db as db

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


def test_open_uses_the_environment_or_home_default_at_call_time(tmp_path, monkeypatch):
    from pathlib import Path

    root = tmp_path / "environment"
    monkeypatch.setenv("HL_DATA", str(root))
    db = store.open()
    db.close()
    assert (root / "catalog.db").exists()
    monkeypatch.delenv("HL_DATA")
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    db = store.open()
    db.close()
    assert (tmp_path / "home" / "home-library" / "catalog.db").exists()


@pytest.mark.parametrize("child", ["captures", "work", "catalog.db"])
def test_open_refuses_private_targets_symlinked_into_a_checkout(tmp_path, child):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    root = tmp_path / "private"
    root.mkdir()
    target = repo / child
    if child == "catalog.db":
        target.touch()
    else:
        target.mkdir()
    (root / child).symlink_to(target)
    with pytest.raises(ValueError, match="git checkout"):
        store.open(root)
    assert not (root / "catalog.db-wal").exists()
    assert list(target.iterdir()) == [] if target.is_dir() else target.read_bytes() == b""


def test_reopening_applies_all_sql_in_a_new_migration_and_preserves_data(tmp_path, monkeypatch):
    root = tmp_path / "private"
    db = store.open(root)
    store.add_location(db, "Shelf A", "shelf", now=NOW)
    db.close()
    directory = migration_directory(tmp_path)
    (directory / "0006_extra.sql").write_text(
        "CREATE TABLE extra (name TEXT); INSERT INTO extra VALUES ('test; text');\n"
        "INSERT INTO extra VALUES ('unterminated but valid final statement')")
    monkeypatch.setattr(store, "files", lambda package: directory)
    db = store.open(root)
    assert db.execute("PRAGMA user_version").fetchone()[0] == 6
    assert [r[0] for r in db.execute("SELECT name FROM extra")] == ["test; text", "unterminated but valid final statement"]
    assert store.locations(db)[0]["name"] == "Shelf A"
    db.close()
    db = store.open(root)
    assert db.execute("SELECT count(*) FROM extra").fetchone()[0] == 2
    db.close()


def test_a_failed_migration_rolls_back_its_schema_and_version(tmp_path, monkeypatch):
    import sqlite3

    root = tmp_path / "private"
    store.open(root).close()
    directory = migration_directory(tmp_path)
    (directory / "0006_broken.sql").write_text("CREATE TABLE extra (id INTEGER);\nCREATE TABLE broken (id")
    monkeypatch.setattr(store, "files", lambda package: directory)
    with pytest.raises(sqlite3.Error):
        store.open(root)
    db = sqlite3.connect(root / "catalog.db")
    assert db.execute("PRAGMA user_version").fetchone()[0] == 5
    assert db.execute("SELECT name FROM sqlite_master WHERE name = 'extra'").fetchall() == []
    db.close()


def test_opening_an_up_to_date_store_does_not_wait_for_another_writer(tmp_path):
    import sqlite3
    import time

    root = tmp_path / "private"
    store.open(root).close()
    writer = sqlite3.connect(root / "catalog.db", isolation_level=None)
    writer.execute("BEGIN IMMEDIATE")  # another process is in the middle of a write
    try:
        started = time.monotonic()
        with store.open(root) as db:
            assert db.execute("PRAGMA user_version").fetchone()[0] == 5
        assert time.monotonic() - started < 1
    finally:
        writer.execute("ROLLBACK")
        writer.close()
