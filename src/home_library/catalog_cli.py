"""Catalog commands for agents and people, using the same store as the app."""
import argparse
import csv
import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

from home_library import maintenance, records, store, worker


def add_commands(parser, commands):
    """Add catalog commands without changing the photo pipeline's arguments."""
    parser.add_argument("--data-root", type=Path, help="private data directory (default: $HL_DATA or ~/home-library)")
    worker_command = commands.add_parser("worker", help="Drain queued captures one at a time.")
    worker_command.add_argument("--once", action="store_true")
    data_root(worker_command)
    data_root(commands.add_parser("token", help="Rotate and print the agent token."))
    backup = commands.add_parser("backup", help="Snapshot the catalog and mirror private photos and work.")
    backup.add_argument("destination", type=Path)
    data_root(backup)
    catalog = commands.add_parser("catalog", help="Read and change the catalog.")
    data_root(catalog)
    actions = catalog.add_subparsers(dest="catalog_command", required=True)
    books = actions.add_parser("books", help="List books as JSON lines.")
    books.add_argument("--q", default="")
    books.add_argument("--state")
    books.add_argument("--location")
    show = actions.add_parser("show", help="Print one book as JSON.")
    show.add_argument("id", type=int)
    edit = actions.add_parser("edit", help="Change a book at the version you read.")
    edit.add_argument("id", type=int)
    edit.add_argument("--version", type=int, required=True)
    edit.add_argument("changes", nargs="+")
    move = actions.add_parser("move", help="Move selected books or change their state.")
    move.add_argument("ids", type=int, nargs="+")
    move.add_argument("--location")
    move.add_argument("--state")
    actions.add_parser("locations", help="List locations as JSON lines.")
    add = actions.add_parser("add-location", help="Add a shelf or box.")
    add.add_argument("name")
    add.add_argument("--kind", required=True)
    export = actions.add_parser("export", help="Print the complete catalog as CSV or JSON.")
    format = export.add_mutually_exclusive_group(required=True)
    format.add_argument("--csv", action="store_true")
    format.add_argument("--json", action="store_true")
    for sub in actions.choices.values():
        data_root(sub)


def data_root(parser):
    """Accept the root after a command without overwriting a root supplied before it."""
    parser.add_argument("--data-root", type=Path, default=argparse.SUPPRESS, help=argparse.SUPPRESS)


def _location(db, name):
    if name is None:
        return None
    match = next((row for row in store.locations(db) if row["name"] == name), None)
    if match is None:
        raise store.NotFound("location was not found; use hl catalog locations")
    return match["id"]


def _print(value):
    print(json.dumps(value, ensure_ascii=False))


def _catalog(db, args):
    action = args.catalog_command
    if action == "books":
        location_id = _location(db, args.location)
        offset = 0
        while True:
            rows = store.search_books(db, args.q, state=args.state, location_id=location_id, offset=offset)
            for row in rows:
                _print(row)
            if len(rows) < 50:
                break
            offset += len(rows)
    elif action == "export":
        rows = store.export_rows(db)
        if args.json:
            _print(rows)
        else:
            sys.stdout.write("\ufeff")
            writer = csv.writer(sys.stdout)
            columns = records.COLUMNS[:19]
            writer.writerow(columns)
            for row in rows:
                writer.writerow([records.csv_cell(row[key] if row[key] is not None else "") for key in columns])
    elif action == "show":
        _print(store.book(db, args.id))
    elif action == "edit":
        changes = {}
        for pair in args.changes:
            field, equals, value = pair.partition("=")
            if not equals:
                raise store.Invalid("edits must be field=value pairs")
            if field in ("age_from", "age_to", "location_id"):
                try:
                    value = int(value) if value else None
                except ValueError as error:
                    raise store.Invalid(f"{field} must be an integer or empty") from error
            elif field == "needs_review":
                if value not in ("true", "false", ""):
                    raise store.Invalid("needs_review must be true or false")
                value = value == "true"
            elif field == "cover_capture_id" and not value:
                value = None
            changes[field] = value
        _print(store.update_book(db, args.id, args.version, changes, "agent"))
    elif action == "move":
        for row in store.move_books(db, args.ids, location_id=_location(db, args.location),
                                    state=args.state, by="agent"):
            _print(row)
    elif action == "locations":
        for row in store.locations(db):
            _print(row)
    elif action == "add-location":
        _print(store.add_location(db, args.name, args.kind))


def execute(args, *, run=subprocess.run, popen=subprocess.Popen):
    """Report store errors on one line so shell and agent callers can handle them."""
    try:
        if args.command == "worker":
            return worker.run(args.data_root, once=args.once, popen=popen)
        if args.command == "token":
            print(maintenance.rotate_token(args.data_root))
        elif args.command == "backup":
            maintenance.backup(args.data_root, args.destination, run=run)
        else:
            with closing(store.open(args.data_root)) as db:
                _catalog(db, args)
        return 0
    except (ValueError, store.NotFound, OSError, sqlite3.Error, subprocess.SubprocessError) as error:
        print(" ".join(str(error).splitlines()), file=sys.stderr)
        return 1
