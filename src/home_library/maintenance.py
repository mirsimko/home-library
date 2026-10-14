"""Private data maintenance that never puts secrets in a checkout."""
import hashlib
import json
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import tempfile
from contextlib import closing, suppress
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from home_library import store
from home_library.workspace import refuse_inside_checkout

KEPT = 14
RECORD = "backup.json"


def data_root(root=None):
    """Resolve the configured private directory at call time, including symlinks."""
    return refuse_inside_checkout(root if root is not None else os.environ.get("HL_DATA") or Path.home() / "home-library")


def rotate_token(root=None):
    """Replace the hash atomically with owner-only permissions, then return the new secret."""
    root = data_root(root)
    refuse_inside_checkout(root / "agent-token")
    root.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    _write_private(root / "agent-token", hashlib.sha256(token.encode("utf-8")).hexdigest() + "\n")
    return token


def _write_private(target, text):
    """Replace target atomically with a file only its owner can read."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, delete=False) as handle:
            temporary = Path(handle.name)
            os.fchmod(handle.fileno(), 0o600)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def backup_record(root):
    """The outcome of the last backup (last_success, failed_at, error); empty when none was recorded or it is damaged."""
    try:
        record = json.loads((Path(root) / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return record if isinstance(record, dict) else {}


def _record(root, now, error=None):
    """Note in the data root that a backup succeeded at now, or failed with error; a success clears the failure."""
    refuse_inside_checkout(root / RECORD)
    stamp = now.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    last = backup_record(root).get("last_success")
    record = {"last_success": last if error else stamp, "failed_at": stamp if error else None, "error": error}
    _write_private(root / RECORD, json.dumps(record) + "\n")


def backup(root, destination, *, run=subprocess.run, now=None, force=False):
    """Take a catalog snapshot and mirror photo evidence, refusing destructive overlaps and empty sources.

    The outcome is noted in the data root (backup.json) for the Status page, unless the root has no catalog.
    """
    now = now or datetime.now()
    root = data_root(root)
    try:
        _backup(root, destination, run, now, force)
    except Exception as error:
        if (root / "catalog.db").is_file():
            with suppress(OSError, ValueError):
                _record(root, now, " ".join(str(error).splitlines()) or type(error).__name__)
        raise
    _record(root, now)


def _backup(root, destination, run, now, force):
    destination = refuse_inside_checkout(destination)
    earlier = _dated(destination / "snapshots", r"catalog-(\d{8})\.db")
    today = max(now.date(), earlier[-1][0]) if earlier else now.date()  # a clock set back must not reuse an older day
    snapshot = destination / "snapshots" / f"catalog-{today:%Y%m%d}.db"
    kept = destination / "deleted" / f"{today:%Y%m%d}" / f"{now:%H%M%S}"
    _refuse_overlap(root, [destination, *(destination / name for name in ("catalog.db", "snapshots", "deleted", "captures", "work")),
                           snapshot, kept.parent, kept, *(kept / name for name in ("captures", "work"))])
    if not (root / "catalog.db").is_file():
        raise ValueError(f"{root} has no catalog.db; is HL_DATA right? Nothing was backed up")
    destination.mkdir(parents=True, exist_ok=True)
    latest = destination / "catalog.db"
    with closing(store.open(root)) as db:
        if not force and (earlier or latest.is_file()):
            _refuse_shrunken(db, earlier[-1][1] if earlier else latest)
        if not earlier and latest.is_file():
            _keep_old_style(latest, destination / "snapshots", today)
        store.backup_database(db, snapshot)
    _copy_over(snapshot, destination / "catalog.db")
    for _, old in _dated(destination / "snapshots", r"catalog-(\d{8})\.db")[:-KEPT]:
        old.unlink()
    for name in ("captures", "work"):
        run(["rsync", "-a", "--delete", "--backup", f"--backup-dir={kept / name}",
             f"{root}/{name}/", f"{destination}/{name}/"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    for day, old in _dated(destination / "deleted", r"(\d{8})"):
        if day <= today - timedelta(days=KEPT):
            _forget(old)


def _refuse_overlap(root, paths):
    """Raise when any path, symlinks followed, lies in the data root, holds it, or lies in a checkout."""
    for path in paths:
        target = refuse_inside_checkout(path)
        if target.is_relative_to(root) or root.is_relative_to(target):
            raise ValueError(f"backup destination must not overlap the data root: {path} resolves to {target}")


def _refuse_shrunken(db, earlier):
    """Raise when the catalog holds under half the books of the earlier copy, or that copy cannot be read."""
    try:
        with closing(sqlite3.connect(f"{earlier.as_uri()}?mode=ro", uri=True)) as old:
            before = old.execute("SELECT count(*) FROM books").fetchone()[0]
    except sqlite3.Error as error:
        raise ValueError(f"cannot read the earlier copy {earlier.name}: {error}; use --force to override") from error
    now = db.execute("SELECT count(*) FROM books").fetchone()[0]
    if now * 2 < before:
        raise ValueError(f"the catalog has {now} of the {before} books in the earlier copy ({earlier.name}); "
                         "refusing to back up, use --force to override")


def _keep_old_style(latest, snapshots, today):
    """Save the catalog of a backup made before snapshots under the day it was written, before it is replaced."""
    day = min(date.fromtimestamp(latest.stat().st_mtime), today - timedelta(days=1))
    while (snapshots / f"catalog-{day:%Y%m%d}.db").exists():
        day -= timedelta(days=1)
    snapshots.mkdir(exist_ok=True)
    _copy_over(latest, snapshots / f"catalog-{day:%Y%m%d}.db")


def _copy_over(source, target):
    """Replace target with a copy of source in one step."""
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".catalog-", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        shutil.copyfile(source, temporary)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def _forget(path):
    """Remove a dated directory with what it holds, or a stray link or file, never following a link."""
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def _dated(directory, pattern):
    """List (day, entry) for the entries of directory named by pattern, whose group is a date, oldest first."""
    found = []
    for path in directory.iterdir() if directory.is_dir() else ():
        match = re.fullmatch(pattern, path.name)
        if match:
            with suppress(ValueError):  # a name that only looks like a date is not ours
                found.append((datetime.strptime(match[1], "%Y%m%d").date(), path))
    return sorted(found)
