"""The private catalog and job queue, shared by every app writer."""
import sqlite3
from importlib.resources import files

from home_library.workspace import refuse_inside_checkout


def open(data_root):
    """Open a private WAL database and apply each packaged migration once."""
    root = refuse_inside_checkout(data_root)
    root.mkdir(parents=True, exist_ok=True)
    for directory in ("captures", "work"):
        (root / directory).mkdir(exist_ok=True)
    db = sqlite3.connect(root / "catalog.db")
    try:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA journal_mode = WAL")
        migrations = sorted(files("home_library.migrations").iterdir(), key=lambda path: path.name)
        for migration in migrations:
            if not migration.name.endswith(".sql"):
                continue
            version = int(migration.name.split("_", 1)[0])
            db.execute("BEGIN IMMEDIATE")
            if version > db.execute("PRAGMA user_version").fetchone()[0]:
                # executescript commits an existing transaction; execute complete statements instead.
                statement = ""
                for line in migration.read_text(encoding="utf-8").splitlines(keepends=True):
                    statement += line
                    if sqlite3.complete_statement(statement):
                        db.execute(statement)
                        statement = ""
                db.execute(f"PRAGMA user_version = {version}")
            db.commit()
    except BaseException:
        db.close()
        raise
    return db
