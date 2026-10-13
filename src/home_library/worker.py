"""Drain the private queue one capture at a time, keeping evidence separate from books."""
import json
import logging
import os
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import closing, contextmanager

from home_library import maintenance, store
from home_library.workspace import refuse_inside_checkout

LOG = logging.getLogger(__name__)
EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
HEARTBEAT_FAILURES = 3  # consecutive failed renewals after which the lease counts as lost
COMMANDS = {"shelf": "run", "cover": "cover", "barcode": "barcode"}


def _job(db, root, job, popen, heartbeat_interval, timeout, killpg, stop):
    capture = job["capture"]
    photo = root / "captures" / f"{capture['id']}.{EXTENSIONS[capture['media_type']]}"
    command = [sys.executable, "-m", "home_library.cli", "--work-root", str(root / "work"),
               COMMANDS[capture["kind"]], str(photo), "--location", job["location"]]
    LOG.info("job %s capture %s started", job["id"], capture["id"])
    with tempfile.TemporaryFile() as errors:
        try:
            target = root / "work" / capture["id"] / "records.json"
            refuse_inside_checkout(photo)
            refuse_inside_checkout(target)
            # A child must produce evidence this time, even when a previous attempt left records behind.
            target.unlink(missing_ok=True)
            child = popen(command, start_new_session=True, stdin=subprocess.DEVNULL,
                          stdout=subprocess.DEVNULL, stderr=errors)
            done, lost = threading.Event(), threading.Event()
            lease = threading.Thread(target=_heartbeat,
                                     args=(root, job, child, done, lost, heartbeat_interval, killpg))
            lease.start()
            try:
                code, timed_out = _wait(child, timeout, stop, lost, killpg)
            finally:
                done.set()
                lease.join()
            if stop.is_set():
                _release(db, job)
                return
            if lost.is_set():
                LOG.warning("job %s no longer owned", job["id"])
                return
            if timed_out:
                _fail(db, job, errors, "child timeout")
                return
            if code:
                _fail(db, job, errors, f"child exited with status {code}")
                return
            rows = json.loads(target.read_text(encoding="utf-8"))
            store.finish_job(db, job["id"], job["owner"], rows)
        except store.Conflict:
            LOG.warning("job %s no longer owned", job["id"])
            return
        except sqlite3.Error:
            LOG.warning("job %s could not be recorded; its lease runs out and another attempt takes over", job["id"])
            return
        except (OSError, ValueError):
            _fail(db, job, errors, "records.json is missing, unreadable or invalid, or the child could not start")
            return
    LOG.info("job %s capture %s finished", job["id"], capture["id"])


def _release(db, job):
    """The worker killed the child on purpose, so the job goes back at once and the stop costs no attempt."""
    try:
        store.release_job(db, job["id"], job["owner"])
        LOG.info("job %s stopped and given back", job["id"])
    except store.Conflict:
        LOG.warning("job %s no longer owned", job["id"])
    except sqlite3.Error:
        LOG.warning("job %s could not be given back; it is taken over when its lease goes stale", job["id"])


def _wait(child, timeout, stop, lost, killpg):
    deadline = time.monotonic() + timeout
    while True:
        if stop.is_set():
            _kill(child, killpg)
            return child.wait(), False
        if lost.is_set():
            return child.wait(), False
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _kill(child, killpg)
            return child.wait(), True
        try:
            return child.wait(timeout=min(0.1, remaining)), False
        except subprocess.TimeoutExpired:
            pass


def _kill(child, killpg):
    try:
        killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass  # The child can finish between deciding to kill it and delivering the signal.


def _heartbeat(root, job, child, done, lost, interval, killpg):
    # SQLite connections belong to the thread that opened them.
    failures = 0
    try:
        with closing(store.open(root)) as db:
            while not done.wait(interval):
                try:
                    kept = store.heartbeat(db, job["id"], job["owner"])
                    failures = 0
                except sqlite3.Error:
                    # A busy database passes; only a lease that cannot be renewed three times running is lost.
                    failures += 1
                    LOG.warning("job %s heartbeat failed (%s in a row)", job["id"], failures)
                    if failures < HEARTBEAT_FAILURES:
                        continue
                    raise
                if not kept:
                    lost.set()
                    _kill(child, killpg)
                    return
    except Exception:
        # Without lease renewal, leave the job for takeover rather than trusting a late result.
        LOG.warning("job %s heartbeat unavailable", job["id"])
        lost.set()
        _kill(child, killpg)


def _fail(db, job, errors, reason):
    errors.flush()
    size = errors.seek(0, 2)
    errors.seek(max(0, size - 8000))
    tail = errors.read().decode("utf-8", errors="replace")[-2000:]
    try:
        store.fail_job(db, job["id"], job["owner"], reason + ("\n" + tail if tail else ""))
        LOG.warning("job %s failed", job["id"])
    except store.Conflict:
        LOG.warning("job %s no longer owned", job["id"])
    except sqlite3.Error:
        LOG.warning("job %s failure could not be recorded; its lease runs out and another attempt takes over", job["id"])


@contextmanager
def _signals(stop):
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        for sig in previous:
            signal.signal(sig, lambda number, frame: stop.set())
        yield
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def run(root=None, *, once=False, popen=subprocess.Popen, heartbeat_interval=30, timeout=1200,
        idle_wait=5, killpg=os.killpg, stop=None):
    """Handle at most one job with once, or keep draining the queue in order."""
    root = maintenance.data_root(root)
    stop = stop if stop is not None else threading.Event()
    with _signals(stop), closing(store.open(root)) as db:
        while not stop.is_set():
            job = None
            try:
                job = store.claim_job(db)
                if job is not None:
                    _job(db, root, job, popen, heartbeat_interval, timeout, killpg, stop)
            except sqlite3.Error:
                # A busy or briefly unavailable database must not end the service; look again after the wait.
                LOG.warning("database error%s", f" in job {job['id']}" if job else " while claiming a job")
                if once:
                    return 0
                stop.wait(idle_wait)
                continue
            if once:
                return 0
            if job is None:
                stop.wait(idle_wait)
    return 0
