"""Drain the private queue one capture at a time, keeping evidence separate from books."""
import json
import logging
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import closing

from home_library import maintenance, store

LOG = logging.getLogger(__name__)
EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
COMMANDS = {"shelf": "run", "cover": "cover", "barcode": "barcode"}


def _job(db, root, job, popen, heartbeat_interval, killpg):
    capture = job["capture"]
    photo = root / "captures" / f"{capture['id']}.{EXTENSIONS[capture['media_type']]}"
    command = [sys.executable, "-m", "home_library.cli", "--work-root", str(root / "work"),
               COMMANDS[capture["kind"]], str(photo), "--location", job["location"]]
    LOG.info("job %s capture %s started", job["id"], capture["id"])
    with tempfile.TemporaryFile() as errors:
        try:
            target = root / "work" / capture["id"] / "records.json"
            # A child must produce evidence this time, even when a previous attempt left records behind.
            target.unlink(missing_ok=True)
            child = popen(command, start_new_session=True, stdin=subprocess.DEVNULL,
                          stdout=subprocess.DEVNULL, stderr=errors)
            done, lost = threading.Event(), threading.Event()
            lease = threading.Thread(target=_heartbeat,
                                     args=(root, job, child, done, lost, heartbeat_interval, killpg))
            lease.start()
            try:
                code = child.wait()
            finally:
                done.set()
                lease.join()
            if lost.is_set():
                LOG.warning("job %s no longer owned", job["id"])
                return
            if code:
                _fail(db, job, errors, f"child exited with status {code}")
                return
            rows = json.loads(target.read_text(encoding="utf-8"))
            store.finish_job(db, job["id"], job["owner"], rows)
        except store.Conflict:
            LOG.warning("job %s no longer owned", job["id"])
            return
        except (OSError, ValueError):
            _fail(db, job, errors, "records.json is missing, unreadable or invalid, or the child could not start")
            return
    LOG.info("job %s capture %s finished", job["id"], capture["id"])


def _kill(child, killpg):
    try:
        killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass  # The child can finish between deciding to kill it and delivering the signal.


def _heartbeat(root, job, child, done, lost, interval, killpg):
    # SQLite connections belong to the thread that opened them.
    with closing(store.open(root)) as db:
        while not done.wait(interval):
            if not store.heartbeat(db, job["id"], job["owner"]):
                lost.set()
                _kill(child, killpg)
                return


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


def run(root=None, *, once=False, popen=subprocess.Popen, heartbeat_interval=30, killpg=os.killpg):
    """Handle at most one job with once, or keep draining the queue in order."""
    root = maintenance.data_root(root)
    with closing(store.open(root)) as db:
        while True:
            job = store.claim_job(db)
            if job is not None:
                _job(db, root, job, popen, heartbeat_interval, killpg)
            if once:
                return 0
            if job is None:
                time.sleep(5)
