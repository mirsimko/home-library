"""Drain the private queue one capture at a time, keeping evidence separate from books."""
import json
import logging
import subprocess
import sys
import tempfile
import time
from contextlib import closing

from home_library import maintenance, store

LOG = logging.getLogger(__name__)
EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
COMMANDS = {"shelf": "run", "cover": "cover", "barcode": "barcode"}


def _job(db, root, job, popen):
    capture = job["capture"]
    photo = root / "captures" / f"{capture['id']}.{EXTENSIONS[capture['media_type']]}"
    command = [sys.executable, "-m", "home_library.cli", "--work-root", str(root / "work"),
               COMMANDS[capture["kind"]], str(photo), "--location", job["location"]]
    LOG.info("job %s capture %s started", job["id"], capture["id"])
    with tempfile.TemporaryFile() as errors:
        child = popen(command, start_new_session=True, stdin=subprocess.DEVNULL,
                      stdout=subprocess.DEVNULL, stderr=errors)
        child.wait()
        rows = json.loads((root / "work" / capture["id"] / "records.json").read_text(encoding="utf-8"))
        store.finish_job(db, job["id"], job["owner"], rows)
    LOG.info("job %s capture %s finished", job["id"], capture["id"])


def run(root=None, *, once=False, popen=subprocess.Popen):
    """Handle at most one job with once, or keep draining the queue in order."""
    root = maintenance.data_root(root)
    with closing(store.open(root)) as db:
        while True:
            job = store.claim_job(db)
            if job is not None:
                _job(db, root, job, popen)
            if once:
                return 0
            if job is None:
                time.sleep(5)
