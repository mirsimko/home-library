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


def item(title, language, status="accepted", reason="agreed"):
    return {"status": status, "reason": reason, "title": title, "language": language, "exact": True,
            "readings": [{"read_id": "a-sol", **entry(1, title, language)}]}


def store_merged(photo_dir, items):
    merged = {"file": "shelf-1.jpg", "reads": ["a-sol", "b-spark"], "items": items,
              "unreadable": [], "parse_errors": []}
    (photo_dir / "merged.json").write_text(json.dumps(merged, ensure_ascii=False), encoding="utf-8")


def test_looking_up_a_photo_stores_candidates_for_each_fully_read_title(tmp_path):
    store_merged(tmp_path, [
        item("だるまさんが", "ja"),
        item("Zelen", "cs", status="review", reason="partial"),
        item("Zelený drak", "cs", status="review", reason="solo"),
    ])
    ndl_answer = (FIXTURES / "ndl_search_daruma.xml").read_bytes()
    no_czech_record = (FIXTURES / "nkcr_empty.txt").read_text(encoding="utf-8")

    candidates = pipeline.lookup_photo(
        tmp_path, fetch=lambda url: ndl_answer, run_yaz=lambda commands: no_czech_record)

    assert candidates == load(tmp_path / "lookup" / "candidates.json")
    assert candidates["file"] == "shelf-1.jpg"
    daruma, drak = candidates["books"]  # the partly read title is not looked up
    assert (daruma["item"], daruma["title"], daruma["language"]) == (0, "だるまさんが", "ja")
    assert "ndl:000009209109" in [c["id"] for c in daruma["candidates"]]
    assert (drak["item"], drak["title"], drak["candidates"]) == (2, "Zelený drak", [])
    assert {"source": "nkcr", "step": "title", "status": "no_match", "count": 0} in drak["queries"]
