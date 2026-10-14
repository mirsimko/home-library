"""Tokens and backups stay private, using temporary roots only."""
import base64
import hashlib
import stat
from pathlib import Path

import pytest

from home_library.cli import main


@pytest.mark.parametrize("position", ["before", "after", "environment", "home"])
def test_token_rotation_prints_random_secret_and_saves_only_its_private_hash(tmp_path, capsys, monkeypatch, position):
    root = tmp_path / "private" if position != "home" else tmp_path / "home-library"
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("HL_DATA", raising=False)
    args = ["token"]
    if position == "environment":
        monkeypatch.setenv("HL_DATA", str(root))
    elif position in ("before", "after"):
        index = 0 if position == "before" else 1
        args[index:index] = ["--data-root", str(root)]
    root.mkdir()
    target = root / "agent-token"
    target.write_text("old hash")
    target.chmod(0o644)
    secrets = []
    for _ in range(2):
        assert main(args) == 0
        output = capsys.readouterr()
        token = output.out.strip()
        assert len(output.out.splitlines()) == 1 and output.err == ""
        assert len(base64.urlsafe_b64decode(token + "=")) == 32
        assert target.read_text().strip() == hashlib.sha256(token.encode()).hexdigest()
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
        secrets.append(token)
    assert secrets[0] != secrets[1]


def test_token_refuses_checkout_and_symlinked_checkout_target(tmp_path, capsys):
    checkout = tmp_path / "repo"
    checkout.mkdir()
    (checkout / ".git").mkdir()
    root = tmp_path / "private"
    root.mkdir()
    (root / "agent-token").symlink_to(checkout / "secret")
    for target in (checkout / "data", root):
        assert main(["token", "--data-root", str(target)]) == 1
        output = capsys.readouterr()
        assert output.out == "" and "git checkout" in output.err
    assert not (checkout / "secret").exists()


@pytest.mark.parametrize("position", ["before", "after", "environment"])
def test_backup_vacuums_rows_and_mirrors_private_directories(tmp_path, capsys, monkeypatch, position):
    import sqlite3

    from store_helpers import typed_book

    from home_library import store

    root, destination = tmp_path / "private", tmp_path / "backup"
    db = store.open(root)
    original = typed_book(db)
    db.close()
    destination.mkdir()
    (destination / "catalog.db").write_text("older snapshot")
    monkeypatch.setenv("HL_DATA", str(root))
    args = ["backup", str(destination)]
    if position != "environment":
        index = 0 if position == "before" else len(args)
        args[index:index] = ["--data-root", str(root)]
    calls = []

    def rsync(command, **kwargs):
        calls.append((command, kwargs))

    assert main(args, run=rsync) == 0
    assert capsys.readouterr().err == ""
    copy = sqlite3.connect(destination / "catalog.db")
    copy.row_factory = sqlite3.Row
    assert store.book(copy, original["id"]) == original
    copy.close()
    assert [(call[0][:3], call[0][-2:]) for call in calls] == [
        (["rsync", "-a", "--delete"], [f"{root}/captures/", f"{destination}/captures/"]),
        (["rsync", "-a", "--delete"], [f"{root}/work/", f"{destination}/work/"]),
    ]
    assert all(call[1]["check"] is True for call in calls)


def test_backup_refuses_checkout_and_overlapping_roots_before_copying(tmp_path, capsys):
    root = tmp_path / "private"
    root.mkdir()
    checkout = tmp_path / "repo"
    checkout.mkdir()
    (checkout / ".git").write_text("gitdir: elsewhere")
    called = []
    for destination in (checkout / "backup", root, root / "backup", tmp_path):
        assert main(["backup", str(destination), "--data-root", str(root)],
                    run=lambda *a, **k: called.append(a)) == 1
        assert len(capsys.readouterr().err.splitlines()) == 1
    assert called == [] and not (root / "catalog.db").exists()


def test_backup_reports_rsync_failure(tmp_path, capsys):
    import subprocess

    def rsync(command, **kwargs):
        raise subprocess.CalledProcessError(12, command)

    from home_library import store

    store.open(tmp_path / "private").close()
    assert main(["backup", str(tmp_path / "backup"), "--data-root", str(tmp_path / "private")], run=rsync) == 1
    output = capsys.readouterr()
    assert output.out == "" and len(output.err.splitlines()) == 1
    assert "12" in output.err
