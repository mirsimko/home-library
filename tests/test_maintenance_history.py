"""A backup keeps dated history, so a bad night cannot replace the only good copy."""
import sqlite3
from datetime import date

import pytest
from store_helpers import typed_book

from home_library import maintenance, store


def source(tmp_path, books=1):
    root = tmp_path / "private"
    db = store.open(root)
    for number in range(books):
        typed_book(db, title=f"Kniha {number}")
    db.close()
    return root


def titles(path):
    with sqlite3.connect(path) as copy:
        return sorted(row[0] for row in copy.execute("SELECT title FROM books"))


def run_backup(root, destination, day, **options):
    maintenance.backup(root, destination, run=lambda *a, **k: None, today=date.fromisoformat(day), **options)


def test_backup_keeps_the_latest_copy_and_a_dated_snapshot(tmp_path):
    root, destination = source(tmp_path), tmp_path / "backup"
    run_backup(root, destination, "2026-10-14")
    assert titles(destination / "catalog.db") == ["Kniha 0"]
    assert titles(destination / "snapshots" / "catalog-20261014.db") == ["Kniha 0"]
    db = store.open(root)
    typed_book(db, title="Druhá")
    db.close()
    run_backup(root, destination, "2026-10-14")
    run_backup(root, destination, "2026-10-15")
    assert sorted(path.name for path in (destination / "snapshots").iterdir()) == [
        "catalog-20261014.db", "catalog-20261015.db"]
    assert titles(destination / "snapshots" / "catalog-20261014.db") == ["Druhá", "Kniha 0"]
    assert titles(destination / "catalog.db") == ["Druhá", "Kniha 0"]


def test_backup_keeps_only_the_fourteen_latest_snapshots(tmp_path):
    root, destination = source(tmp_path), tmp_path / "backup"
    snapshots = destination / "snapshots"
    snapshots.mkdir(parents=True)
    for day in range(1, 21):
        (snapshots / f"catalog-202610{day:02d}.db").write_text("old")
    (snapshots / "notes.txt").write_text("not a snapshot")
    run_backup(root, destination, "2026-10-21")
    names = sorted(path.name for path in snapshots.iterdir())
    assert names == [*(f"catalog-202610{day:02d}.db" for day in range(8, 22)), "notes.txt"]
