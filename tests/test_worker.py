"""The queue worker runs fake children and imports evidence through the public store."""
import json
import sys
from pathlib import Path

import pytest
from PIL import Image
from store_helpers import CAPTURE_ID, SECOND_ID, capture, record

from home_library import store, worker


class Child:
    """A Popen stand-in that writes invented records into the requested work directory."""

    def __init__(self, rows=None, returncode=0, stderr=""):
        self.rows = [record("The Copper Comet")] if rows is None else rows
        self.returncode = returncode
        self.stderr = stderr
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        root = Path(command[command.index("--work-root") + 1])
        photo = Path(command[6])
        directory = root / photo.stem
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "records.json").write_text(json.dumps(self.rows), encoding="utf-8")
        kwargs["stderr"].write(self.stderr.encode("utf-8"))
        return self

    def wait(self, timeout=None):
        return self.returncode


def queued(root, *, kind="shelf", media_type="image/jpeg", id=CAPTURE_ID):
    db = store.open(root)
    receipt = capture(db, id, kind=kind, media_type=media_type)
    extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[media_type]
    Image.new("RGB", (20, 20), "white").save(root / "captures" / f"{id}.{extension}")
    db.close()
    return receipt


@pytest.mark.parametrize("kind, command, media_type, extension", [
    ("shelf", "run", "image/jpeg", "jpg"),
    ("cover", "cover", "image/png", "png"),
    ("barcode", "barcode", "image/webp", "webp"),
])
def test_once_runs_one_capture_in_a_separate_group_and_imports_records(tmp_path, kind, command, media_type, extension, caplog):
    root = tmp_path / "private"
    queued(root, kind=kind, media_type=media_type)
    queued(root, id=SECOND_ID)
    child = Child()
    with caplog.at_level("INFO"):
        assert worker.run(root, once=True, popen=child) == 0
    (args, kwargs), = child.calls
    assert args == [sys.executable, "-m", "home_library.cli", "--work-root", str(root / "work"), command,
                    str(root / "captures" / f"{CAPTURE_ID}.{extension}"), "--location", "Shelf A"]
    assert kwargs["start_new_session"] is True
    db = store.open(root)
    assert capture(db)["job"]["status"] == "done"
    assert capture(db, SECOND_ID)["job"]["status"] == "queued"
    assert [row["record"] for row in store.observations(db)] == child.rows
    assert store.search_books(db) == []
    db.close()
    assert CAPTURE_ID in caplog.text and "job 1" in caplog.text
    assert "The Copper Comet" not in caplog.text


def test_once_with_no_job_exits_successfully_without_a_child(tmp_path):
    child = Child()
    assert worker.run(tmp_path / "private", once=True, popen=child) == 0
    assert child.calls == []
