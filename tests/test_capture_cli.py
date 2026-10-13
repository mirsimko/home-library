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
