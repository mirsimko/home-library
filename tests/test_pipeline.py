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
        item("Okno do světa Zvířata", "cs", status="review", reason="split"),
    ])
    ndl_answer = (FIXTURES / "ndl_search_daruma.xml").read_bytes()
    no_czech_record = (FIXTURES / "nkcr_empty.txt").read_text(encoding="utf-8")

    candidates = pipeline.lookup_photo(
        tmp_path, fetch=lambda url: ndl_answer, run_yaz=lambda commands: no_czech_record)

    assert candidates == load(tmp_path / "lookup" / "candidates.json")
    assert candidates["file"] == "shelf-1.jpg"
    daruma, drak, okno = candidates["books"]  # the partly read title is not looked up
    assert (okno["item"], okno["title"]) == (3, "Okno do světa Zvířata")
    assert (daruma["item"], daruma["title"], daruma["language"]) == (0, "だるまさんが", "ja")
    assert "ndl:000009209109" in [c["id"] for c in daruma["candidates"]]
    assert (drak["item"], drak["title"], drak["candidates"]) == (2, "Zelený drak", [])
    assert {"source": "nkcr", "step": "title", "status": "no_match", "count": 0} in drak["queries"]


def test_one_reads_answers_for_all_photos_are_gathered_in_the_scoring_shape(tmp_path):
    for stem, title in (("shelf-2", "あかいふうせん"), ("shelf-1", "Zelený drak")):
        store_read(tmp_path / stem, "a-sol", [entry(1, title)])
        read_path = tmp_path / stem / "reads" / "a-sol" / "read.json"
        read_path.write_text(read_path.read_text(encoding="utf-8").replace("shelf-1.jpg", stem + ".jpg"),
                             encoding="utf-8")
    store_read(tmp_path / "shelf-3", "b-spark", [entry(1, "The Blue Kite", "en")])  # another read only

    gathered = pipeline.gather_read(tmp_path, "a-sol")

    assert gathered == {"model": "a-sol", "photos": [
        {"file": "shelf-1.jpg", "books": [entry(1, "Zelený drak")]},
        {"file": "shelf-2.jpg", "books": [entry(1, "あかいふうせん")]},
    ]}


# --- the whole pipeline on one photo, with the model programs and the catalogues faked ---

import csv
from types import SimpleNamespace

from PIL import Image


def answer(*books):
    return json.dumps({"file": "shelf-9.jpg", "books": list(books)}, ensure_ascii=False)


class FakePrograms:
    """Stands in for subprocess.run: the codex read, the pi read and the codex pick."""

    def __init__(self, sol_answer, spark_answer, pick_answer):
        self.sol_answer, self.spark_answer, self.pick_answer = sol_answer, spark_answer, pick_answer
        self.started = []

    def __call__(self, command, **kwargs):
        if command[0] == "pi":
            self.started.append("pi read")
            return SimpleNamespace(returncode=0, stdout=self.spark_answer, stderr="")
        if "-o" in command:
            self.started.append("codex pick")
            Path(command[command.index("-o") + 1]).write_text(self.pick_answer, encoding="utf-8")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        self.started.append("codex read")
        events = [{"type": "item.completed", "item": {"id": "item_0", "type": "agent_message",
                                                      "text": self.sol_answer}}]
        return SimpleNamespace(returncode=0, stdout="\n".join(json.dumps(e) for e in events), stderr="")


def photo_and_programs(tmp_path):
    photo = tmp_path / "phone" / "shelf-9.jpg"
    photo.parent.mkdir()
    Image.new("RGB", (640, 480), "white").save(photo)
    programs = FakePrograms(
        sol_answer=answer(entry(1, "だるまさんが", "ja"), entry(2, "The Blue Kite", "en"), entry(3, "", "unknown", "no")),
        spark_answer=answer(entry(1, "だるまさんが", "ja")),
        pick_answer=json.dumps({"picks": [{"item": 0, "verdict": "match", "candidate_id": "ndl:000009209109",
                                           "reason": "Same title."}]}))
    return photo, programs


def catalogues():
    ndl_answer = (FIXTURES / "ndl_search_daruma.xml").read_bytes()
    nothing = (FIXTURES / "openlibrary_search_empty.json").read_bytes()
    return lambda url: ndl_answer if "ndlsearch" in url else nothing


def test_a_photo_goes_from_tiles_to_review_records_in_one_call(tmp_path):
    photo, programs = photo_and_programs(tmp_path)

    summary = pipeline.run_photo(photo, tmp_path / "work", location="Box 3",
                                 run=programs, fetch=catalogues())

    assert programs.started == ["codex read", "pi read", "codex pick"]
    photo_dir = tmp_path / "work" / "shelf-9"
    with open(photo_dir / "records.csv", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [(r["title"], r["read_status"], r["location"], r["needs_review"]) for r in rows] == [
        ("だるまさんが", "agreed", "Box 3", "true"),
        ("The Blue Kite", "solo", "Box 3", "true"),
        ("", "unreadable", "Box 3", "true"),
    ]
    assert (rows[0]["publisher"], rows[0]["source_id"], rows[0]["sort_key"]) == (
        "ブロンズ新社", "000009209109", "ダルマサン ガ")
    assert (summary["photo"], summary["accepted"], summary["review"], summary["unreadable"]) == (
        "shelf-9.jpg", 1, 1, 1)
    assert summary["directory"] == str(photo_dir)


def test_running_a_photo_again_repeats_no_model_call(tmp_path):
    photo, programs = photo_and_programs(tmp_path)
    pipeline.run_photo(photo, tmp_path / "work", run=programs, fetch=catalogues())
    programs.started.clear()

    summary = pipeline.run_photo(photo, tmp_path / "work", run=programs, fetch=catalogues())

    assert programs.started == []
    assert (summary["accepted"], summary["review"]) == (1, 1)
    assert (tmp_path / "work" / "shelf-9" / "records.csv").exists()


def test_a_read_that_failed_is_the_only_one_repeated(tmp_path):
    photo, programs = photo_and_programs(tmp_path)
    good_answer, programs.spark_answer = programs.spark_answer, ""  # pi returns nothing the first time
    try:
        pipeline.run_photo(photo, tmp_path / "work", run=programs, fetch=catalogues())
    except Exception as failure:
        assert "empty answer" in str(failure)
    else:
        raise AssertionError("the empty second read should have stopped the run")
    programs.started.clear()
    programs.spark_answer = good_answer

    pipeline.run_photo(photo, tmp_path / "work", run=programs, fetch=catalogues())

    assert programs.started == ["pi read", "codex pick"]


def test_a_changed_photo_or_force_runs_everything_again(tmp_path):
    photo, programs = photo_and_programs(tmp_path)
    pipeline.run_photo(photo, tmp_path / "work", run=programs, fetch=catalogues())

    programs.started.clear()
    pipeline.run_photo(photo, tmp_path / "work", run=programs, fetch=catalogues(), force=True)
    assert programs.started == ["codex read", "pi read", "codex pick"]

    programs.started.clear()
    Image.new("RGB", (640, 480), "grey").save(photo)  # another photo under the same name
    pipeline.run_photo(photo, tmp_path / "work", run=programs, fetch=catalogues())
    assert programs.started == ["codex read", "pi read", "codex pick"]


def test_the_summary_reports_how_long_each_read_took(tmp_path):
    photo, programs = photo_and_programs(tmp_path)

    summary = pipeline.run_photo(photo, tmp_path / "work", run=programs, fetch=catalogues())

    assert sorted(summary["seconds"]) == ["a-sol", "b-spark"]
    assert all(isinstance(value, float) and value >= 0 for value in summary["seconds"].values())
