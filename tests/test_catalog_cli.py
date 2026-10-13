"""Agents read the catalog through hl, with temporary data and invented titles."""
import json

import pytest
from store_helpers import typed_book

from home_library import store
from home_library.cli import main


@pytest.mark.parametrize("position", ["before", "catalog", "after", "environment"])
def test_catalog_lists_filters_and_shows_books(tmp_path, capsys, monkeypatch, position):
    root = tmp_path / "private"
    db = store.open(root)
    first = typed_book(db, title="The Copper Comet")
    typed_book(db, title="The Winter Lantern", state="Stored")
    db.close()
    monkeypatch.setenv("HL_DATA", str(root))
    args = ["catalog", "books", "--q", "Copper", "--state", "Active", "--location", "Shelf A"]
    index = {"before": 0, "catalog": 1, "after": len(args)}.get(position)
    if index is not None:
        args[index:index] = ["--data-root", str(root)]
    assert main(args) == 0
    assert [json.loads(line) for line in capsys.readouterr().out.splitlines()] == [first]
    assert main(["catalog", "show", str(first["id"]), "--data-root", str(root)]) == 0
    assert json.loads(capsys.readouterr().out) == first


def test_catalog_adds_and_lists_locations(tmp_path, capsys):
    root = str(tmp_path / "private")
    assert main(["catalog", "add-location", "Winter Box", "--kind", "box", "--data-root", root]) == 0
    added = json.loads(capsys.readouterr().out)
    assert (added["name"], added["kind"]) == ("Winter Box", "box")
    assert main(["--data-root", root, "catalog", "locations"]) == 0
    assert [json.loads(line) for line in capsys.readouterr().out.splitlines()] == [added]


@pytest.mark.parametrize("args, message", [
    (["show", "999"], "not found"),
    (["books", "--location", "Missing"], "location"),
    (["books", "--state", "missing"], "state"),
    (["add-location", "Box", "--kind", "invalid"], "kind"),
])
def test_catalog_errors_are_one_line_and_exit_one(tmp_path, capsys, args, message):
    assert main(["catalog", *args, "--data-root", str(tmp_path / "private")]) == 1
    output = capsys.readouterr()
    assert output.out == "" and len(output.err.splitlines()) == 1
    assert message in output.err


def test_edits_parse_values_and_moves_are_atomic(tmp_path, capsys):
    root = tmp_path / "private"
    db = store.open(root)
    first = typed_book(db, author="Ada Birch", age_to=9)
    second = typed_book(db, title="The Frost Boat")
    box = store.add_location(db, "Winter Box", "box")
    db.close()
    suffix = ["--data-root", str(root)]
    assert main(["catalog", "edit", str(first["id"]), "--version", "1", "age_from=4", "age_to=",
                 "author=", "notes=one=two", *suffix]) == 0
    edited = json.loads(capsys.readouterr().out)
    assert (edited["age_from"], edited["age_to"], edited["author"], edited["notes"], edited["version"]) == (
        4, None, "", "one=two", 2)
    assert edited["reviewed_by"] == "agent"
    assert main(["catalog", "move", str(first["id"]), str(second["id"]), "--location", "Winter Box",
                 "--state", "Stored", *suffix]) == 0
    moved = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [(b["id"], b["state"], b["location_id"]) for b in moved] == [
        (first["id"], "Stored", box["id"]), (second["id"], "Stored", box["id"])]
    assert main(["catalog", "move", str(first["id"]), "999", "--state", "Gone", *suffix]) == 1
    capsys.readouterr()
    db = store.open(root)
    assert store.book(db, first["id"])["state"] == "Stored"
    db.close()


@pytest.mark.parametrize("tail, message", [
    (["--version", "0", "title=Other"], "changed"),
    (["--version", "1", "age_from=four"], "integer"),
    (["--version", "1", "title="], "title"),
    (["--version", "1", "id=2"], "editable"),
    (["--version", "1", "author"], "field=value"),
])
def test_bad_edits_leave_books_unchanged(tmp_path, capsys, tail, message):
    root = tmp_path / "private"
    db = store.open(root)
    original = typed_book(db)
    db.close()
    assert main(["catalog", "edit", "1", *tail, "--data-root", str(root)]) == 1
    output = capsys.readouterr()
    assert output.out == "" and len(output.err.splitlines()) == 1 and message in output.err
    db = store.open(root)
    assert store.book(db, 1) == original
    db.close()
