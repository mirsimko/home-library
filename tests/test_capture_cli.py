import csv
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from home_library.cli import main


def read_program(command, **kwargs):
    answer = json.dumps({"books": [{"title": "The Amber Kite", "author": "Ada Reed",
                                   "readable": "yes", "language": "unknown"}]})
    if command[0] == "pi":
        return SimpleNamespace(returncode=0, stdout=answer, stderr="")
    events = [{"type": "item.completed", "item": {"type": "agent_message", "text": answer}},
              {"type": "turn.completed"}]
    return SimpleNamespace(returncode=0, stdout="\n".join(json.dumps(event) for event in events), stderr="")


@pytest.mark.parametrize("root_first", [False, True])
def test_cover_writes_json_and_csv_and_prints_one_summary(tmp_path, capsys, root_first):
    photo = tmp_path / "cover.jpg"
    Image.new("RGB", (640, 480), "white").save(photo)
    args = ["cover", str(photo), "--location", "Shelf 4"]
    root = ["--work-root", str(tmp_path / "work")]

    assert main(root + args if root_first else args + root, run=read_program) == 0

    directory = tmp_path / "work" / "cover"
    (record,) = json.loads((directory / "records.json").read_text())
    assert (record["title"], record["author"], record["location"]) == ("The Amber Kite", "Ada Reed", "Shelf 4")
    with open(directory / "records.csv", encoding="utf-8-sig", newline="") as handle:
        assert list(csv.DictReader(handle))[0]["title"] == "The Amber Kite"
    output = capsys.readouterr()
    assert output.err == "" and len(output.out.splitlines()) == 1
    assert "cover.jpg: 1 accepted" in output.out and str(directory / "records.csv") in output.out


def test_cover_exits_one_and_reports_a_missing_photo(tmp_path, capsys):
    assert main(["cover", str(tmp_path / "missing.jpg"), "--work-root", str(tmp_path / "work")],
                run=read_program) == 1
    output = capsys.readouterr()
    assert "missing.jpg" in output.err and "FileNotFoundError" in output.err and output.out == ""


@pytest.mark.parametrize("root_first", [False, True])
def test_barcode_writes_records_and_prints_one_summary_without_running_a_model(tmp_path, capsys, root_first):
    from barcode_helpers import ean13

    photo = tmp_path / "barcode.png"
    ean13("9780000000002").save(photo)
    asked = []

    def fetch(url):
        asked.append(url)
        return b'{"ISBN:9780000000002": {"title": "The Amber Kite", "key": "/books/invented"}}' if "openlibrary" in url else b'<searchRetrieveResponse xmlns="http://www.loc.gov/zing/srw/"/>'

    def no_program(*args, **kwargs):
        raise AssertionError("a barcode must not run a model or yaz-client for an English ISBN")

    args = ["barcode", str(photo), "--location", "Box 5"]
    root = ["--work-root", str(tmp_path / "work")]
    assert main(root + args if root_first else args + root, run=no_program, fetch=fetch, run_yaz=no_program) == 0
    directory = tmp_path / "work" / "barcode"
    (record,) = json.loads((directory / "records.json").read_text())
    assert (record["title"], record["catalogue_title"], record["isbn"], record["read_status"], record["location"]) == (
        "", "The Amber Kite", "9780000000002", "barcode", "Box 5")
    with open(directory / "records.csv", encoding="utf-8-sig", newline="") as handle:
        assert list(csv.DictReader(handle))[0]["catalogue_title"] == "The Amber Kite"
    output = capsys.readouterr()
    assert output.err == "" and len(output.out.splitlines()) == 1
    assert "barcode.png:" in output.out and str(directory / "records.csv") in output.out
    assert len(asked) == 2


@pytest.mark.parametrize("command", ["cover", "barcode"])
def test_capture_commands_refuse_a_work_root_inside_a_checkout(tmp_path, capsys, command):
    (tmp_path / ".git").mkdir()
    photo = tmp_path / "photo.png"
    Image.new("RGB", (30, 30), "white").save(photo)
    assert main([command, str(photo), "--work-root", str(tmp_path / "work")], run=read_program) == 1
    assert "git checkout" in capsys.readouterr().err and not (tmp_path / "work").exists()


def test_barcode_exits_one_and_reports_a_missing_photo(tmp_path, capsys):
    assert main(["barcode", str(tmp_path / "missing.png"), "--work-root", str(tmp_path / "work")]) == 1
    output = capsys.readouterr()
    assert "missing.png" in output.err and "FileNotFoundError" in output.err and output.out == ""
