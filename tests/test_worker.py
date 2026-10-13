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
                    str(root / "captures" / f"{CAPTURE_ID}.{extension}"), "--location=Shelf A"]
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


def test_timeout_kills_the_process_group_and_keeps_the_stderr_tail(tmp_path):
    import signal

    root = tmp_path / "private"
    queued(root)
    child = HangingChild()
    child.stderr = "timeout detail"
    assert worker.run(root, once=True, popen=child, timeout=0.03, killpg=child.killpg) == 0
    assert child.kills == [(child.pid, signal.SIGKILL)]
    db = store.open(root)
    job = capture(db)["job"]
    assert job["status"] == "queued" and "timeout" in job["error"]
    assert job["error"].endswith("timeout detail") and store.observations(db) == []
    db.close()


def test_timeout_stops_a_real_fake_hl_and_its_descendant(tmp_path):
    import os
    import signal
    import subprocess

    root = tmp_path / "private"
    queued(root)
    script = tmp_path / "fake_hl.py"
    pid_file = tmp_path / "descendant.pid"
    script.write_text(
        "import subprocess, sys, time\n"
        "from pathlib import Path\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"Path({str(pid_file)!r}).write_text(str(child.pid))\n"
        "print('invented hang diagnostic', file=sys.stderr, flush=True)\n"
        "time.sleep(60)\n")
    children, groups = [], []

    def popen(command, **kwargs):
        child = subprocess.Popen([sys.executable, str(script), *command[3:]], **kwargs)
        children.append(child)
        return child

    def killpg(pid, sig):
        groups.append((pid, sig))
        os.killpg(pid, sig)

    try:
        assert worker.run(root, once=True, popen=popen, timeout=0.5, killpg=killpg) == 0
        assert groups == [(children[0].pid, signal.SIGKILL)]
        assert children[0].returncode == -signal.SIGKILL
        descendant = Path(f"/proc/{pid_file.read_text()}/stat")
        assert not descendant.exists() or descendant.read_text().split()[2] == "Z"
        db = store.open(root)
        assert capture(db)["job"]["error"].endswith("invented hang diagnostic\n")
        assert store.observations(db) == []
        db.close()
    finally:
        for child in children:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL)
            child.wait()


def test_stopping_kills_the_child_and_gives_its_job_back_to_the_queue(tmp_path):
    import signal
    import threading
    from concurrent.futures import ThreadPoolExecutor

    root = tmp_path / "private"
    queued(root)
    child, stop = HangingChild(), threading.Event()
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(worker.run, root, popen=child, stop=stop, killpg=child.killpg, heartbeat_interval=0.01)
        try:
            assert child.started.wait(2)
            stop.set()
            assert result.result(timeout=3) == 0
        finally:
            child.exited.set()
    assert child.kills == [(child.pid, signal.SIGKILL)]
    db = store.open(root)
    job = capture(db)["job"]
    assert job["status"] == "queued" and job["owner"] is None and job["attempts"] == 0
    assert job["error"] is None and store.observations(db) == []
    assert store.claim_job(db)["attempts"] == 1  # a restart takes it at once, and the stop cost nothing
    db.close()


@pytest.mark.parametrize("interval", [5, 0.01])
def test_idle_wait_is_injectable_and_can_be_interrupted(tmp_path, interval):
    import threading

    class StopAfterWait(threading.Event):
        def wait(self, timeout=None):
            self.waits.append(timeout)
            self.set()
            return True

    stop, child = StopAfterWait(), Child()
    stop.waits = []
    assert worker.run(tmp_path / "private", stop=stop, idle_wait=interval, popen=child) == 0
    assert stop.waits == [interval] and child.calls == []


def test_a_heartbeat_connection_failure_stops_the_child_and_preserves_the_lease(tmp_path, caplog):
    root = tmp_path / "private"
    queued(root)
    child = HangingChild()

    def unavailable(command, **kwargs):
        result = child(command, **kwargs)
        (root / ".git").mkdir()  # The heartbeat's own store connection must now refuse this root.
        return result

    try:
        assert worker.run(root, once=True, popen=unavailable, heartbeat_interval=0.01,
                          timeout=0.1, killpg=child.killpg) == 0
    finally:
        (root / ".git").rmdir()
    db = store.open(root)
    assert capture(db)["job"]["status"] == "running"
    assert store.observations(db) == []
    db.close()
    assert "job 1" in caplog.text and "The Copper Comet" not in caplog.text
    assert len(child.kills) == 1


def test_worker_refuses_symlinked_work_in_a_checkout_before_removing_old_evidence(tmp_path):
    root = tmp_path / "private"
    queued(root)
    checkout = tmp_path / "repo"
    checkout.mkdir()
    (checkout / ".git").mkdir()
    old = checkout / "records.json"
    old.write_text("old evidence")
    (root / "work" / CAPTURE_ID).symlink_to(checkout, target_is_directory=True)
    child = Child()
    assert worker.run(root, once=True, popen=child) == 0
    assert child.calls == [] and old.read_text() == "old evidence"
    db = store.open(root)
    assert capture(db)["job"]["status"] == "queued" and store.observations(db) == []
    db.close()


def run_with_flaky_heartbeat(tmp_path, failures):
    """Run one job whose heartbeat raises `failures` times in a row (None: always) before working again."""
    import sqlite3
    import time
    from concurrent.futures import ThreadPoolExecutor

    root = tmp_path / "private"
    queued(root)
    child, real, calls = HangingChild(), store.heartbeat, []

    def flaky(db, job_id, owner, now=None):
        calls.append(job_id)
        if failures is None or len(calls) <= failures:
            raise sqlite3.OperationalError("database is locked")
        return real(db, job_id, owner, now)

    store.heartbeat = flaky
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(worker.run, root, once=True, popen=child, heartbeat_interval=0.01,
                                 killpg=child.killpg, timeout=5)
            assert child.started.wait(2)
            deadline = time.monotonic() + 2
            while len(calls) < (failures or 3) + 2 and not child.exited.is_set() and time.monotonic() < deadline:
                time.sleep(0.005)
            child.exited.set()
            assert result.result(timeout=3) == 0
    finally:
        store.heartbeat = real
    return root, child


def test_a_heartbeat_that_fails_now_and_then_does_not_kill_the_child(tmp_path):
    root, child = run_with_flaky_heartbeat(tmp_path, 2)
    assert child.kills == []
    db = store.open(root)
    assert capture(db)["job"]["status"] == "done"
    db.close()


def test_three_failed_heartbeats_in_a_row_count_as_a_lost_lease(tmp_path):
    root, child = run_with_flaky_heartbeat(tmp_path, None)
    assert len(child.kills) == 1
    db = store.open(root)
    assert capture(db)["job"]["status"] == "running" and store.observations(db) == []
    db.close()


class StopAfterWaits(__import__("threading").Event):
    """A stop signal that records each idle wait and fires on the n-th."""

    def __init__(self, after):
        super().__init__()
        self.after, self.waits = after, []

    def wait(self, timeout=None):
        self.waits.append(timeout)
        if len(self.waits) >= self.after:
            self.set()
        return self.is_set()


def test_a_database_error_when_claiming_waits_and_the_loop_goes_on(tmp_path, monkeypatch):
    import sqlite3

    root = tmp_path / "private"
    queued(root)
    real, calls = store.claim_job, []

    def locked(db, now=None):
        calls.append(now)
        if len(calls) == 1:
            raise sqlite3.OperationalError("database is locked")
        return real(db, now)

    monkeypatch.setattr(store, "claim_job", locked)
    stop = StopAfterWaits(2)  # the wait after the error, then the wait once the queue is empty
    assert worker.run(root, popen=Child(), stop=stop, idle_wait=7) == 0
    assert stop.waits == [7, 7]
    db = store.open(root)
    assert capture(db)["job"]["status"] == "done"
    db.close()


@pytest.mark.parametrize("name", ["finish_job", "fail_job"])
def test_a_database_error_when_finishing_or_failing_is_logged_by_job_id_and_does_not_crash(tmp_path, monkeypatch, caplog, name):
    import sqlite3

    root = tmp_path / "private"
    queued(root)

    def locked(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(store, name, locked)
    child = Child(returncode=0 if name == "finish_job" else 3)
    assert worker.run(root, once=True, popen=child) == 0
    assert "job 1" in caplog.text and "The Copper Comet" not in caplog.text
    db = store.open(root)
    assert capture(db)["job"]["status"] == "running"  # the lease runs out and another attempt takes over
    db.close()


def test_a_location_that_starts_with_a_dash_cannot_be_read_as_an_option(tmp_path):
    from home_library import cli

    root = tmp_path / "private"
    queued(root)
    db = store.open(root)
    store.rename_location(db, 1, "-x")
    db.close()
    child = Child()
    assert worker.run(root, once=True, popen=child) == 0
    (args, _), = child.calls
    assert args[-1] == "--location=-x"
    assert cli._parser().parse_args(args[3:]).location == "-x"  # the real command line parser agrees
