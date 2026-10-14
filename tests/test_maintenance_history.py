"""A backup keeps dated history, so a bad night cannot replace the only good copy."""
import shutil
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


def test_rsync_keeps_deleted_and_replaced_photos_in_a_dated_directory(tmp_path):
    root, destination = source(tmp_path), tmp_path / "backup"
    calls = []
    maintenance.backup(root, destination, run=lambda command, **kwargs: calls.append(command),
                       today=date(2026, 10, 15))
    assert calls == [
        ["rsync", "-a", "--delete", "--backup", f"--backup-dir={destination}/deleted/20261015/{name}",
         f"{root}/{name}/", f"{destination}/{name}/"] for name in ("captures", "work")
    ]


@pytest.mark.skipif(shutil.which("rsync") is None, reason="needs rsync")
def test_real_rsync_mirrors_and_keeps_what_the_mirror_drops(tmp_path):
    root, destination = source(tmp_path), tmp_path / "backup"
    (root / "captures" / "gone.jpg").write_bytes(b"gone")
    (root / "captures" / "changed.jpg").write_bytes(b"first")
    (root / "work" / "p1").mkdir()
    (root / "work" / "p1" / "tile.png").write_bytes(b"tile")
    maintenance.backup(root, destination, today=date(2026, 10, 14))
    (root / "captures" / "gone.jpg").unlink()
    (root / "captures" / "changed.jpg").write_bytes(b"second")
    shutil.rmtree(root / "work" / "p1")
    maintenance.backup(root, destination, today=date(2026, 10, 15))
    kept = destination / "deleted" / "20261015"
    assert not (destination / "captures" / "gone.jpg").exists()
    assert (destination / "captures" / "changed.jpg").read_bytes() == b"second"
    assert (kept / "captures" / "gone.jpg").read_bytes() == b"gone"
    assert (kept / "captures" / "changed.jpg").read_bytes() == b"first"
    assert (kept / "work" / "p1" / "tile.png").read_bytes() == b"tile"
    assert not (destination / "deleted" / "20261014").exists()


def test_backup_drops_deleted_directories_older_than_fourteen_days(tmp_path):
    root, destination = source(tmp_path), tmp_path / "backup"
    deleted = destination / "deleted"
    for name in ("20260930", "20261001", "20261002", "20261015", "elsewhere"):
        (deleted / name).mkdir(parents=True)
        (deleted / name / "photo.jpg").write_text("kept")
    run_backup(root, destination, "2026-10-15")
    assert sorted(path.name for path in deleted.iterdir()) == ["20261002", "20261015", "elsewhere"]


@pytest.mark.parametrize("name", ["snapshots", "deleted"])
def test_backup_refuses_history_directories_that_lead_into_the_data_root_or_a_checkout(tmp_path, name):
    root, destination = source(tmp_path), tmp_path / "backup"
    checkout = tmp_path / "repo"
    checkout.mkdir()
    (checkout / ".git").write_text("gitdir: elsewhere")
    destination.mkdir()
    for target in (root / "captures", checkout / "history"):
        (destination / name).symlink_to(target)
        called = []
        with pytest.raises(ValueError):
            maintenance.backup(root, destination, run=lambda *a, **k: called.append(a), today=date(2026, 10, 15))
        assert called == [] and not (checkout / "history").exists()
        (destination / name).unlink()
