"""A backup leaves its outcome in the data root, so the Status page can show a refused or missing one."""
import json
import stat
import subprocess
from contextlib import closing
from datetime import datetime, timezone

import pytest
from store_helpers import typed_book
from test_maintenance_history import shrink, source

from home_library import maintenance, store
from home_library.cli import main


def at(day, hour=3):
    return datetime.fromisoformat(f"{day}T{hour:02d}:30:00").replace(tzinfo=timezone.utc)


def record(root):
    return json.loads((root / "backup.json").read_text())


def attempt(root, destination, when, **options):
    maintenance.backup(root, destination, run=lambda *a, **k: None, now=when, **options)


def test_a_backup_records_when_it_last_succeeded_in_a_private_file(tmp_path):
    root, destination = source(tmp_path), tmp_path / "backup"
    attempt(root, destination, at("2026-10-14"))
    assert record(root) == {"last_success": "2026-10-14T03:30:00Z", "failed_at": None, "error": None}
    assert stat.S_IMODE((root / "backup.json").stat().st_mode) == 0o600
    attempt(root, destination, at("2026-10-15"))
    assert record(root)["last_success"] == "2026-10-15T03:30:00Z"
    assert not [path for path in root.iterdir() if path.name.startswith(".")]


def test_a_refused_backup_records_when_and_why_and_keeps_the_last_success(tmp_path):
    root, destination = source(tmp_path, books=4), tmp_path / "backup"
    attempt(root, destination, at("2026-10-14"))
    shrink(root, keep=1)
    with pytest.raises(ValueError):
        attempt(root, destination, at("2026-10-15"))
    saved = record(root)
    assert saved["last_success"] == "2026-10-14T03:30:00Z" and saved["failed_at"] == "2026-10-15T03:30:00Z"
    assert "1 of the 4 books" in saved["error"] and "--force" in saved["error"]
    attempt(root, destination, at("2026-10-16"), force=True)
    assert record(root) == {"last_success": "2026-10-16T03:30:00Z", "failed_at": None, "error": None}


def test_an_overlapping_destination_and_a_failing_rsync_are_recorded_too(tmp_path):
    root = source(tmp_path)
    with pytest.raises(ValueError):
        attempt(root, root / "backup", at("2026-10-15"))
    assert record(root)["failed_at"] == "2026-10-15T03:30:00Z" and "overlap" in record(root)["error"]

    def rsync(command, **kwargs):
        raise subprocess.CalledProcessError(12, command)

    with pytest.raises(subprocess.CalledProcessError):
        maintenance.backup(root, tmp_path / "backup", run=rsync, now=at("2026-10-16"))
    assert record(root)["failed_at"] == "2026-10-16T03:30:00Z" and "12" in record(root)["error"]
    assert record(root)["last_success"] is None


def test_a_root_without_a_catalog_gets_no_record(tmp_path):
    root = tmp_path / "wrong"
    root.mkdir()
    with pytest.raises(ValueError, match="catalog.db"):
        attempt(root, tmp_path / "backup", at("2026-10-15"))
    assert list(root.iterdir()) == []


def test_a_refusal_from_the_command_line_is_recorded(tmp_path, capsys):
    root, destination = tmp_path / "private", tmp_path / "backup"
    with closing(store.open(root)) as db:
        for number in range(4):
            typed_book(db, title=f"Kniha {number}")
    args = ["backup", str(destination), "--data-root", str(root)]
    assert main(args, run=lambda *a, **k: None) == 0
    shrink(root, keep=1)
    assert main(args, run=lambda *a, **k: None) == 1
    assert "--force" in record(root)["error"] and record(root)["last_success"] is not None
    capsys.readouterr()


def test_the_record_reads_as_nothing_when_missing_or_damaged(tmp_path):
    assert maintenance.backup_record(tmp_path) == {}
    (tmp_path / "backup.json").write_text("{not json")
    assert maintenance.backup_record(tmp_path) == {}
