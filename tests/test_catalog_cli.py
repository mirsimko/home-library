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
