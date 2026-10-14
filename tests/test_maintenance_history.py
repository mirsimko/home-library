"""A backup keeps dated history, so a bad night cannot replace the only good copy."""
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime

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
    maintenance.backup(root, destination, run=lambda *a, **k: None, now=datetime.fromisoformat(f"{day}T03:30:00"), **options)


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
    run_backup(root, destination, "2026-10-01")
    for day in range(2, 21):
        shutil.copy(snapshots / "catalog-20261001.db", snapshots / f"catalog-202610{day:02d}.db")
    (snapshots / "notes.txt").write_text("not a snapshot")
    run_backup(root, destination, "2026-10-21")
    names = sorted(path.name for path in snapshots.iterdir())
    assert names == [*(f"catalog-202610{day:02d}.db" for day in range(8, 22)), "notes.txt"]


def test_rsync_keeps_deleted_and_replaced_photos_in_a_directory_of_the_run(tmp_path):
    root, destination = source(tmp_path), tmp_path / "backup"
    calls = []
    maintenance.backup(root, destination, run=lambda command, **kwargs: calls.append(command),
                       now=datetime(2026, 10, 15, 3, 30))
    assert calls == [
        ["rsync", "-a", "--delete", "--backup", f"--backup-dir={destination}/deleted/20261015/033000/{name}",
         f"{root}/{name}/", f"{destination}/{name}/"] for name in ("captures", "work")
    ]


@pytest.mark.skipif(shutil.which("rsync") is None, reason="needs rsync")
def test_real_rsync_mirrors_and_keeps_what_the_mirror_drops(tmp_path):
    root, destination = source(tmp_path), tmp_path / "backup"
    (root / "captures" / "gone.jpg").write_bytes(b"gone")
    (root / "captures" / "changed.jpg").write_bytes(b"first")
    (root / "work" / "p1").mkdir()
    (root / "work" / "p1" / "tile.png").write_bytes(b"tile")
    maintenance.backup(root, destination, now=datetime(2026, 10, 14, 3, 30))
    (root / "captures" / "gone.jpg").unlink()
    (root / "captures" / "changed.jpg").write_bytes(b"second")
    shutil.rmtree(root / "work" / "p1")
    maintenance.backup(root, destination, now=datetime(2026, 10, 15, 3, 30))
    kept = destination / "deleted" / "20261015" / "033000"
    assert not (destination / "captures" / "gone.jpg").exists()
    assert (destination / "captures" / "changed.jpg").read_bytes() == b"second"
    assert (kept / "captures" / "gone.jpg").read_bytes() == b"gone"
    assert (kept / "captures" / "changed.jpg").read_bytes() == b"first"
    assert (kept / "work" / "p1" / "tile.png").read_bytes() == b"tile"
    assert not (destination / "deleted" / "20261014").exists()


@pytest.mark.skipif(shutil.which("rsync") is None, reason="needs rsync")
def test_a_photo_replaced_twice_in_a_day_keeps_every_earlier_version(tmp_path):
    root, destination = source(tmp_path), tmp_path / "backup"
    (root / "captures" / "changed.jpg").write_bytes(b"first")
    maintenance.backup(root, destination, now=datetime(2026, 10, 15, 3, 30))
    for version, hour in ((b"second", 9), (b"third", 18)):
        (root / "captures" / "changed.jpg").write_bytes(version)
        maintenance.backup(root, destination, now=datetime(2026, 10, 15, hour, 0))
    kept = destination / "deleted" / "20261015"
    assert sorted(path.name for path in kept.iterdir()) == ["090000", "180000"]
    assert (kept / "090000" / "captures" / "changed.jpg").read_bytes() == b"first"
    assert (kept / "180000" / "captures" / "changed.jpg").read_bytes() == b"second"
    assert (destination / "captures" / "changed.jpg").read_bytes() == b"third"


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
            maintenance.backup(root, destination, run=lambda *a, **k: called.append(a), now=datetime(2026, 10, 15, 3, 30))
        assert called == [] and not (checkout / "history").exists()
        (destination / name).unlink()


def test_backup_refuses_a_data_root_without_a_catalog_and_creates_nothing(tmp_path):
    root, destination = tmp_path / "wrong", tmp_path / "backup"
    called = []
    for force in (False, True):
        with pytest.raises(ValueError, match="catalog.db"):
            maintenance.backup(root, destination, run=lambda *a, **k: called.append(a),
                               now=datetime(2026, 10, 15, 3, 30), force=force)
    root.mkdir()
    with pytest.raises(ValueError, match="catalog.db"):
        run_backup(root, destination, "2026-10-15")
    assert called == [] and list(root.iterdir()) == [] and not destination.exists()


def shrink(root, keep):
    with closing(store.open(root)) as db:
        db.execute("DELETE FROM books WHERE id > ?", (keep,))
        db.commit()


def test_backup_refuses_a_catalog_with_under_half_the_books_of_the_latest_snapshot(tmp_path):
    root, destination = source(tmp_path, books=4), tmp_path / "backup"
    run_backup(root, destination, "2026-10-14")
    shrink(root, keep=1)
    called = []
    with pytest.raises(ValueError, match=r"1 of the 4 books.*--force"):
        maintenance.backup(root, destination, run=lambda *a, **k: called.append(a), now=datetime(2026, 10, 15, 3, 30))
    assert called == [] and len(titles(destination / "catalog.db")) == 4
    assert [path.name for path in (destination / "snapshots").iterdir()] == ["catalog-20261014.db"]
    run_backup(root, destination, "2026-10-15", force=True)
    assert titles(destination / "catalog.db") == ["Kniha 0"]
    assert (destination / "snapshots" / "catalog-20261015.db").is_file()


def test_backup_accepts_exactly_half_the_books(tmp_path):
    root, destination = source(tmp_path, books=4), tmp_path / "backup"
    run_backup(root, destination, "2026-10-14")
    shrink(root, keep=2)
    run_backup(root, destination, "2026-10-15")
    assert len(titles(destination / "catalog.db")) == 2


def test_backup_accepts_an_empty_catalog_when_the_latest_snapshot_is_empty(tmp_path):
    root, destination = source(tmp_path, books=0), tmp_path / "backup"
    run_backup(root, destination, "2026-10-14")
    run_backup(root, destination, "2026-10-15")
    assert titles(destination / "catalog.db") == []


def test_backup_names_an_unreadable_latest_snapshot_and_force_replaces_it(tmp_path):
    root, destination = source(tmp_path), tmp_path / "backup"
    (destination / "snapshots").mkdir(parents=True)
    (destination / "snapshots" / "catalog-20261014.db").write_text("not a database")
    with pytest.raises(ValueError, match=r"catalog-20261014\.db.*--force"):
        run_backup(root, destination, "2026-10-15")
    run_backup(root, destination, "2026-10-15", force=True)
    assert titles(destination / "catalog.db") == ["Kniha 0"]
