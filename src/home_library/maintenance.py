"""Private data maintenance that never puts secrets in a checkout."""
import hashlib
import os
import re
import secrets
import shutil
import subprocess
import tempfile
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

from home_library import store
from home_library.workspace import refuse_inside_checkout


KEPT = 14


def data_root(root=None):
    """Resolve the configured private directory at call time, including symlinks."""
    return refuse_inside_checkout(root if root is not None else os.environ.get("HL_DATA") or Path.home() / "home-library")


def rotate_token(root=None):
    """Replace the hash atomically with owner-only permissions, then return the new secret."""
    root = data_root(root)
    refuse_inside_checkout(root / "agent-token")
    root.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=root, delete=False) as handle:
            temporary = Path(handle.name)
            os.fchmod(handle.fileno(), 0o600)
            handle.write(hashlib.sha256(token.encode("utf-8")).hexdigest() + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(root / "agent-token")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return token


def backup(root, destination, *, run=subprocess.run, today=None):
    """Take a catalog snapshot and mirror photo evidence, refusing destructive overlaps."""
    today = today or date.today()
    root = data_root(root)
    destination = refuse_inside_checkout(destination)
    targets = [destination, *(refuse_inside_checkout(destination / name)
                             for name in ("catalog.db", "captures", "work"))]
    if any(target.is_relative_to(root) or root.is_relative_to(target) for target in targets):
        raise ValueError("backup destination must not overlap the data root")
    destination.mkdir(parents=True, exist_ok=True)
    with closing(store.open(root)) as db:
        snapshot = destination / "snapshots" / f"catalog-{today:%Y%m%d}.db"
        store.backup_database(db, snapshot)
    _copy_over(snapshot, destination / "catalog.db")
    for old in _dated(destination / "snapshots", r"catalog-\d{8}\.db")[:-KEPT]:
        old.unlink()
    for name in ("captures", "work"):
        run(["rsync", "-a", "--delete", "--backup", f"--backup-dir={destination}/deleted/{today:%Y%m%d}/{name}",
             f"{root}/{name}/", f"{destination}/{name}/"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    oldest = f"{today - timedelta(days=KEPT - 1):%Y%m%d}"
    for old in _dated(destination / "deleted", r"\d{8}"):
        if old.name < oldest:
            shutil.rmtree(old)


def _copy_over(source, target):
    """Replace target with a copy of source in one step."""
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".catalog-", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        shutil.copyfile(source, temporary)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def _dated(directory, pattern):
    """List the entries of directory whose names match the dated pattern, oldest first."""
    if not directory.is_dir():
        return []
    return sorted((path for path in directory.iterdir() if re.fullmatch(pattern, path.name)),
                  key=lambda path: path.name)
