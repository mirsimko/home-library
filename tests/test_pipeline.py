"""The stages run on a photo's work directory: each reads plain files and writes plain files."""
import json
from pathlib import Path

from home_library import pipeline

FIXTURES = Path(__file__).parent / "lookup" / "fixtures"


def entry(n, title, language="cs", readable="yes"):
    return {"n": n, "where": "r1c1-r0.jpg", "visible": "spine", "title": title, "other_text": "",
            "language": language, "readable": readable, "confidence": "high", "inferred": ""}


def store_read(photo_dir, read_id, books):
    read = {"file": "shelf-1.jpg", "books": books, "errors": [], "complete": True, "read_id": read_id}
    target = photo_dir / "reads" / read_id
    target.mkdir(parents=True)
    (target / "read.json").write_text(json.dumps(read, ensure_ascii=False), encoding="utf-8")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_merging_a_photo_stores_what_the_two_reads_agree_on(tmp_path):
    store_read(tmp_path, "a-sol", [entry(1, "Zelený drak"), entry(2, "The Blue Kite", "en")])
    store_read(tmp_path, "b-spark", [entry(1, "Zelený drak")])

    merged = pipeline.merge_photo(tmp_path, ["a-sol", "b-spark"])

    assert merged == load(tmp_path / "merged.json")
    assert merged["reads"] == ["a-sol", "b-spark"]
    assert [(i["title"], i["status"], i["reason"]) for i in merged["items"]] == [
        ("Zelený drak", "accepted", "agreed"),
        ("The Blue Kite", "review", "solo"),
    ]
