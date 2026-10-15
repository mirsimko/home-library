"""A backup is a real standalone SQLite snapshot, even when the source uses WAL."""
import sqlite3

import pytest
from store_helpers import db as db
from store_helpers import typed_book

from home_library import store


def test_vacuum_backup_replaces_old_copy_with_all_committed_rows(db, tmp_path):
    first = typed_book(db)
    destination = tmp_path / "backup's" / "catalog.db"
    store.backup_database(db, destination)
    with sqlite3.connect(destination) as copy:
        copy.row_factory = sqlite3.Row
        assert store.book(copy, first["id"]) == first
    second = typed_book(db, title="The Glass Orchard")
    statements = []
    db.set_trace_callback(statements.append)
    store.backup_database(db, destination)
    db.set_trace_callback(None)
    assert any(sql.startswith("VACUUM INTO ") for sql in statements)
    copy = sqlite3.connect(destination)
    copy.row_factory = sqlite3.Row
    assert store.book(copy, second["id"]) == second
    copy.close()
    assert list(destination.parent.iterdir()) == [destination]


def test_failed_vacuum_preserves_previous_copy_and_cleans_temporary_file(db, tmp_path):
    destination = tmp_path / "backup" / "catalog.db"
    original = typed_book(db)
    store.backup_database(db, destination)
    db.execute("BEGIN")
    with pytest.raises(sqlite3.OperationalError):
        store.backup_database(db, destination)
    db.rollback()
    copy = sqlite3.connect(destination)
    copy.row_factory = sqlite3.Row
    assert store.book(copy, original["id"]) == original
    copy.close()
    assert list(destination.parent.iterdir()) == [destination]


def test_vacuum_backup_refuses_checkout(db, tmp_path):
    checkout = tmp_path / "repo"
    checkout.mkdir()
    (checkout / ".git").mkdir()
    with pytest.raises(ValueError, match="git checkout"):
        store.backup_database(db, checkout / "catalog.db")
    assert not (checkout / "catalog.db").exists()
