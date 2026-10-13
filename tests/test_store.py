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
