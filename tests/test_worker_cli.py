"""The worker command exposes one-job runs to shell and agent harnesses."""
import pytest
from test_worker import Child, queued

from home_library import store
from home_library.cli import main


@pytest.mark.parametrize("position", ["before", "after", "environment"])
def test_worker_once_accepts_data_root_and_exits_zero(tmp_path, monkeypatch, position):
    root = tmp_path / "private"
    queued(root)
    child = Child()
    monkeypatch.setenv("HL_DATA", str(root))
    args = ["worker", "--once"]
    if position != "environment":
        index = 0 if position == "before" else len(args)
        args[index:index] = ["--data-root", str(root)]
    assert main(args, popen=child) == 0
    assert len(child.calls) == 1
    db = store.open(root)
    assert len(store.observations(db)) == 1
    db.close()
    assert main(args, popen=child) == 0 and len(child.calls) == 1


def test_worker_refuses_a_data_root_in_a_checkout(tmp_path, capsys):
    (tmp_path / ".git").mkdir()
    child = Child()
    assert main(["worker", "--once", "--data-root", str(tmp_path / "data")], popen=child) == 1
    assert "git checkout" in capsys.readouterr().err and child.calls == []
