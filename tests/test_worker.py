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


@pytest.mark.parametrize("problem, message", [
    ("exit", "exit"), ("missing", "records.json"), ("garbage", "records.json"),
    ("encoding", "records.json"), ("directory", "records.json"), ("shape", "records"),
])
def test_failed_children_keep_diagnostics_and_import_nothing(tmp_path, caplog, problem, message):
    root = tmp_path / "private"
    queued(root)
    stderr = "discarded prefix" + "ž" * 2100
    child = Child(returncode=7 if problem == "exit" else 0, stderr=stderr)

    def broken(command, **kwargs):
        result = child(command, **kwargs)
        target = root / "work" / CAPTURE_ID / "records.json"
        if problem == "missing":
            target.unlink()
        elif problem == "garbage":
            target.write_text('{"broken":')
        elif problem == "encoding":
            target.write_bytes(b"\xff")
        elif problem == "directory":
            target.unlink()
            target.mkdir()
        elif problem == "shape":
            target.write_text('[{"title": 3}]')
        return result

    assert worker.run(root, once=True, popen=broken) == 0
    db = store.open(root)
    job = capture(db)["job"]
    assert job["status"] == "queued" and job["attempts"] == 1
    assert message in job["error"] and job["error"].endswith("ž" * 2000)
    assert "discarded prefix" not in job["error"]
    assert store.observations(db) == []
    db.close()
    assert "The Copper Comet" not in caplog.text and "ž" not in caplog.text


def test_a_late_finish_is_logged_by_job_id_and_does_not_crash(tmp_path, caplog):
    from datetime import datetime, timedelta, timezone

    root = tmp_path / "private"
    queued(root)
    child = Child()

    def takeover(command, **kwargs):
        result = child(command, **kwargs)
        db = store.open(root)
        stolen = store.claim_job(db, datetime.now(timezone.utc) + timedelta(minutes=21))
        assert stolen["attempts"] == 2
        db.close()
        return result

    assert worker.run(root, once=True, popen=takeover) == 0
    assert "job 1" in caplog.text and "The Copper Comet" not in caplog.text
    db = store.open(root)
    assert capture(db)["job"]["status"] == "running" and store.observations(db) == []
    db.close()


def test_a_child_that_writes_nothing_cannot_import_an_old_records_file(tmp_path):
    root = tmp_path / "private"
    queued(root)
    target = root / "work" / CAPTURE_ID / "records.json"
    target.parent.mkdir()
    target.write_text(json.dumps([record("The Old Lantern")]))

    def empty(command, **kwargs):
        return Child()

    assert worker.run(root, once=True, popen=empty) == 0
    db = store.open(root)
    assert store.observations(db) == [] and capture(db)["job"]["status"] == "queued"
    db.close()


class HangingChild(Child):
    """An injectable process that waits until released or its process group is killed."""

    def __init__(self):
        import threading

        super().__init__()
        self.started = threading.Event()
        self.exited = threading.Event()
        self.pid = 45678
        self.kills = []

    def __call__(self, command, **kwargs):
        super().__call__(command, **kwargs)
        self.started.set()
        return self

    def wait(self, timeout=None):
        import subprocess

        if not self.exited.wait(timeout):
            raise subprocess.TimeoutExpired("fake hl", timeout)
        return self.returncode

    def killpg(self, pid, signal):
        self.kills.append((pid, signal))
        self.returncode = -signal
        self.exited.set()


def test_heartbeats_refresh_while_the_child_runs(tmp_path):
    import time
    from concurrent.futures import ThreadPoolExecutor

    root = tmp_path / "private"
    queued(root)
    child = HangingChild()
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(worker.run, root, once=True, popen=child, heartbeat_interval=0.01,
                             killpg=child.killpg)
        try:
            assert child.started.wait(2)
            db = store.open(root)
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                job = capture(db)["job"]
                if job["heartbeat_at"] > job["started_at"]:
                    break
                time.sleep(0.005)
            else:
                pytest.fail("the child's lease was never refreshed")
            assert job["status"] == "running" and store.observations(db) == []
            db.close()
        finally:
            child.exited.set()
        assert result.result(timeout=3) == 0
    assert child.kills == []


def test_lost_heartbeat_kills_the_group_and_imports_nothing(tmp_path):
    import signal
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime, timedelta, timezone

    root = tmp_path / "private"
    queued(root)
    child = HangingChild()
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(worker.run, root, once=True, popen=child, heartbeat_interval=0.01,
                             killpg=child.killpg)
        try:
            assert child.started.wait(2)
            db = store.open(root)
            current = store.claim_job(db, datetime.now(timezone.utc) + timedelta(minutes=21))
            assert current["attempts"] == 2
            assert child.exited.wait(2)
            assert result.result(timeout=3) == 0
            assert capture(db)["job"]["owner"] == current["owner"]
            assert store.observations(db) == []
            db.close()
        finally:
            child.exited.set()
    assert child.kills == [(child.pid, signal.SIGKILL)]
