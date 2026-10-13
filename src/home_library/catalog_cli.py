"""Catalog commands for agents and people, using the same store as the app."""
import argparse
import json
import sys
from contextlib import closing
from pathlib import Path

from home_library import store


def add_commands(parser, commands):
    """Add catalog commands without changing the photo pipeline's arguments."""
    parser.add_argument("--data-root", type=Path, help="private data directory (default: $HL_DATA or ~/home-library)")
    catalog = commands.add_parser("catalog", help="Read and change the catalog.")
    data_root(catalog)
    actions = catalog.add_subparsers(dest="catalog_command", required=True)
    books = actions.add_parser("books", help="List books as JSON lines.")
    books.add_argument("--q", default="")
    books.add_argument("--state")
    books.add_argument("--location")
    show = actions.add_parser("show", help="Print one book as JSON.")
    show.add_argument("id", type=int)
    actions.add_parser("locations", help="List locations as JSON lines.")
    add = actions.add_parser("add-location", help="Add a shelf or box.")
    add.add_argument("name")
    add.add_argument("--kind", required=True)
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
        for row in store.search_books(db, args.q, state=args.state, location_id=_location(db, args.location)):
            _print(row)
    elif action == "show":
        _print(store.book(db, args.id))
    elif action == "locations":
        for row in store.locations(db):
            _print(row)
    elif action == "add-location":
        _print(store.add_location(db, args.name, args.kind))


def execute(args, **kwargs):
    """Report store errors on one line so shell and agent callers can handle them."""
    try:
        with closing(store.open(args.data_root)) as db:
            _catalog(db, args)
        return 0
    except (ValueError, store.NotFound, OSError) as error:
        print(" ".join(str(error).splitlines()), file=sys.stderr)
        return 1
