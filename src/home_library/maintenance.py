"""Private data maintenance that never puts secrets in a checkout."""
import hashlib
import os
import secrets
import subprocess
import tempfile
from contextlib import closing
from pathlib import Path

from home_library import store
from home_library.workspace import refuse_inside_checkout


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


def backup(root, destination, *, run=subprocess.run):
    """Take a catalog snapshot and mirror photo evidence, refusing destructive overlaps."""
    root = data_root(root)
    destination = refuse_inside_checkout(destination)
    targets = [destination, *(refuse_inside_checkout(destination / name)
                             for name in ("catalog.db", "captures", "work"))]
    if any(target.is_relative_to(root) or root.is_relative_to(target) for target in targets):
        raise ValueError("backup destination must not overlap the data root")
    destination.mkdir(parents=True, exist_ok=True)
    with closing(store.open(root)) as db:
        store.backup_database(db, destination / "catalog.db")
    for name in ("captures", "work"):
        run(["rsync", "-a", "--delete", f"{root}/{name}/", f"{destination}/{name}/"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
