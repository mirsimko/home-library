"""The stages run on a photo's work directory: each reads plain files and writes plain files."""
import csv
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from home_library import pipeline
from home_library.lookup.errors import Unavailable
from home_library.reader import run_read
from home_library.tiles import cut_tiles

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


def answer(*books):
    return json.dumps({"file": "shelf-9.jpg", "books": list(books)}, ensure_ascii=False)


class FakePrograms:
    """Stands in for subprocess.run: the codex read, the pi read and the codex pick."""

    def __init__(self, sol_answer, spark_answer, pick_answer):
        self.sol_answer, self.spark_answer, self.pick_answer = sol_answer, spark_answer, pick_answer
        self.pick_returncode = 0
        self.started = []

    def __call__(self, command, **kwargs):
        if command[0] == "pi":
            self.started.append("pi read")
            return SimpleNamespace(returncode=0, stdout=self.spark_answer, stderr="")
        if "-o" in command:
            self.started.append("codex pick")
            Path(command[command.index("-o") + 1]).write_text(self.pick_answer, encoding="utf-8")
            return SimpleNamespace(returncode=self.pick_returncode, stdout="", stderr="")
        self.started.append("codex read")
        events = [{"type": "item.completed", "item": {"id": "item_0", "type": "agent_message",
                                                      "text": self.sol_answer}},
                  {"type": "turn.completed", "usage": {"input_tokens": 100, "output_tokens": 5}}]
        return SimpleNamespace(returncode=0, stdout="\n".join(json.dumps(e) for e in events), stderr="")


def photo_and_programs(tmp_path):
    photo = tmp_path / "phone" / "shelf-9.jpg"
    photo.parent.mkdir()
    Image.new("RGB", (640, 480), "white").save(photo)
    programs = FakePrograms(
        sol_answer=answer(entry(1, "だるまさんが", "ja"), entry(2, "The Blue Kite", "en"), entry(3, "", "unknown", "no")),
        spark_answer=answer(entry(1, "だるまさんが", "ja")),
        pick_answer=json.dumps({"picks": [{"book": 1, "title": "だるまさんが", "verdict": "match",
                                           "candidate_id": "ndl:000009209109",
                                           "reason": "Same title."}]}))
    return photo, programs


def run_one(photo, work_root, **options):
    (result,) = pipeline.run_photos([photo], work_root, **options)
    return result


def catalogues():
    ndl_answer = (FIXTURES / "ndl_search_daruma.xml").read_bytes()
    nothing = (FIXTURES / "openlibrary_search_empty.json").read_bytes()
    return lambda url: ndl_answer if "ndlsearch" in url else nothing


def test_a_photo_goes_from_tiles_to_review_records_in_one_call(tmp_path):
    photo, programs = photo_and_programs(tmp_path)

    summary = run_one(photo, tmp_path / "work", location="Box 3",
                                 run=programs, fetch=catalogues())

    assert sorted(programs.started[:2]) == ["codex read", "pi read"]
    assert programs.started[2:] == ["codex pick"]
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
    run_one(photo, tmp_path / "work", run=programs, fetch=catalogues())
    programs.started.clear()

    summary = run_one(photo, tmp_path / "work", run=programs, fetch=catalogues())

    assert programs.started == []
    assert (summary["accepted"], summary["review"]) == (1, 1)
    assert (tmp_path / "work" / "shelf-9" / "records.csv").exists()


def test_a_read_that_failed_is_the_only_one_repeated(tmp_path):
    photo, programs = photo_and_programs(tmp_path)
    good_answer, programs.spark_answer = programs.spark_answer, ""  # pi returns nothing the first time
    failed = run_one(photo, tmp_path / "work", run=programs, fetch=catalogues())
    assert "empty answer" in failed["error"]
    programs.started.clear()
    programs.spark_answer = good_answer

    run_one(photo, tmp_path / "work", run=programs, fetch=catalogues())

    assert programs.started == ["pi read", "codex pick"]


def test_a_changed_photo_or_force_runs_everything_again(tmp_path):
    photo, programs = photo_and_programs(tmp_path)
    run_one(photo, tmp_path / "work", run=programs, fetch=catalogues())

    programs.started.clear()
    run_one(photo, tmp_path / "work", run=programs, fetch=catalogues(), force=True)
    assert sorted(programs.started) == ["codex pick", "codex read", "pi read"]

    programs.started.clear()
    Image.new("RGB", (640, 480), "grey").save(photo)  # another photo under the same name
    run_one(photo, tmp_path / "work", run=programs, fetch=catalogues())
    assert sorted(programs.started) == ["codex pick", "codex read", "pi read"]


def test_the_summary_reports_how_long_each_read_took(tmp_path):
    photo, programs = photo_and_programs(tmp_path)

    summary = run_one(photo, tmp_path / "work", run=programs, fetch=catalogues())

    assert sorted(summary["seconds"]) == ["a-sol", "b-spark"]
    assert all(isinstance(value, float) and value >= 0 for value in summary["seconds"].values())


# --- speed: what may overlap, measured on the home uplink on 2026-10-05 ---


def test_the_two_reads_of_a_photo_run_at_the_same_time(tmp_path):
    photo, programs = photo_and_programs(tmp_path)
    both_running = threading.Barrier(2, timeout=5)  # broken unless the two reads are in progress together

    def run(command, **kwargs):
        if "-o" not in command:
            both_running.wait()
        return programs(command, **kwargs)

    summary = run_one(photo, tmp_path / "work", run=run, fetch=catalogues())

    assert "error" not in summary
    assert (summary["accepted"], summary["review"]) == (1, 1)


def second_photo(tmp_path):
    photo = tmp_path / "phone" / "shelf-10.jpg"
    Image.new("RGB", (640, 480), "grey").save(photo)
    return photo


def test_photos_are_read_one_after_another_and_all_get_their_records(tmp_path):
    first, programs = photo_and_programs(tmp_path)

    results = pipeline.run_photos([first, second_photo(tmp_path)], tmp_path / "work", location="Box 3",
                                  run=programs, fetch=catalogues())

    assert [(r["photo"], r["accepted"], r["review"]) for r in results] == [
        ("shelf-9.jpg", 1, 1), ("shelf-10.jpg", 1, 1)]
    for stem in ("shelf-9", "shelf-10"):
        assert (tmp_path / "work" / stem / "records.csv").exists()


def test_a_photo_that_fails_does_not_stop_the_others(tmp_path):
    first, programs = photo_and_programs(tmp_path)

    results = pipeline.run_photos([tmp_path / "phone" / "missing.jpg", first], tmp_path / "work",
                                  run=programs, fetch=catalogues())

    assert results[0]["photo"] == "missing.jpg" and "error" in results[0]
    assert (results[1]["photo"], results[1]["accepted"]) == ("shelf-9.jpg", 1)
    assert "error" not in results[1]


def test_the_look_ups_of_one_photo_run_while_the_next_photo_is_read(tmp_path):
    # NDL takes 10 to 15 seconds for one title search, so look-ups must not hold up the next photo's reads.
    first, programs = photo_and_programs(tmp_path)
    fetch = catalogues()
    look_up_running, read_running = threading.Event(), threading.Event()
    pi_reads, overlaps = [], []

    def run(command, **kwargs):
        if command[0] == "pi":
            pi_reads.append(command)
            if len(pi_reads) == 2:  # the second photo's read: it must find the first photo's look-up under way
                read_running.set()
                overlaps.append(look_up_running.wait(timeout=5))
        return programs(command, **kwargs)

    def slow_fetch(url):  # a look-up holds on until the next photo is being read
        look_up_running.set()
        overlaps.append(read_running.wait(timeout=5))
        return fetch(url)

    results = pipeline.run_photos([first, second_photo(tmp_path)], tmp_path / "work", run=run, fetch=slow_fetch)

    assert [r["accepted"] for r in results] == [1, 1]
    assert overlaps and all(overlaps)


# --- a rerun never reuses what no longer fits (review council, 2026-10-05) ---


def rows_of(photo_dir):
    with open(photo_dir / "records.csv", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_a_pick_step_that_failed_is_made_again_on_the_next_run(tmp_path):
    photo, programs = photo_and_programs(tmp_path)
    programs.pick_returncode = 1
    run_one(photo, tmp_path / "work", run=programs, fetch=catalogues())
    assert "The pick step failed" in rows_of(tmp_path / "work" / "shelf-9")[0]["notes"]
    programs.started.clear()
    programs.pick_returncode = 0

    run_one(photo, tmp_path / "work", run=programs, fetch=catalogues())

    assert programs.started == ["codex pick"]
    assert rows_of(tmp_path / "work" / "shelf-9")[0]["publisher"] == "ブロンズ新社"


def test_a_pick_is_not_reused_after_a_read_was_made_again(tmp_path):
    photo, programs = photo_and_programs(tmp_path)
    run_one(photo, tmp_path / "work", run=programs, fetch=catalogues())
    photo_dir = tmp_path / "work" / "shelf-9"
    programs.sol_answer = programs.spark_answer = answer(entry(1, "あかいふうせん", "ja"))
    for read_id, backend in pipeline.READERS:  # what `hl read` does
        run_read(photo_dir, read_id, backend, run=programs)
    programs.started.clear()

    run_one(photo, tmp_path / "work", run=programs, fetch=catalogues())

    assert programs.started == ["codex pick"]
    (row,) = rows_of(photo_dir)
    # the fake pick still answers for the old title, which the echo check rejects
    assert (row["title"], row["pick_verdict"], row["catalogue_title"], row["source_id"]) == (
        "あかいふうせん", "none", "", "")


def test_a_changed_photo_whose_read_fails_leaves_nothing_of_the_old_photo(tmp_path):
    photo, programs = photo_and_programs(tmp_path)
    run_one(photo, tmp_path / "work", run=programs, fetch=catalogues())
    Image.new("RGB", (640, 480), "grey").save(photo)
    programs.spark_answer = ""

    failed = run_one(photo, tmp_path / "work", run=programs, fetch=catalogues())

    assert "error" in failed
    photo_dir = tmp_path / "work" / "shelf-9"
    left = sorted(p.name for p in photo_dir.iterdir()) + sorted(p.name for p in (photo_dir / "lookup").iterdir())
    for stale in ("merged.json", "records.csv", "records.json", "candidates.json", "picks.json"):
        assert stale not in left


def test_two_photos_with_the_same_file_name_cannot_share_a_run(tmp_path):
    first, programs = photo_and_programs(tmp_path)
    twin = tmp_path / "other-phone" / "shelf-9.jpg"
    twin.parent.mkdir()
    Image.new("RGB", (640, 480), "grey").save(twin)

    results = pipeline.run_photos([first, twin], tmp_path / "work", run=programs, fetch=catalogues())

    assert "error" not in results[0] and results[0]["accepted"] == 1
    assert "same file name" in results[1]["error"]
    assert sorted(programs.started) == ["codex pick", "codex read", "pi read"]  # the twin was never read


def test_tiles_that_went_missing_are_cut_again_without_reading_again(tmp_path):
    photo, programs = photo_and_programs(tmp_path)
    run_one(photo, tmp_path / "work", run=programs, fetch=catalogues())
    tiles = tmp_path / "work" / "shelf-9" / "tiles"
    (tiles / "r1c1-r180.jpg").unlink()
    programs.started.clear()

    again = run_one(photo, tmp_path / "work", run=programs, fetch=catalogues())

    assert "error" not in again and programs.started == []
    assert sorted(p.name for p in tiles.iterdir()) == ["r1c1-r0.jpg", "r1c1-r180.jpg"]


def test_a_stored_read_that_cannot_be_decoded_is_made_again(tmp_path):
    photo, programs = photo_and_programs(tmp_path)
    run_one(photo, tmp_path / "work", run=programs, fetch=catalogues())
    (tmp_path / "work" / "shelf-9" / "reads" / "b-spark" / "read.json").write_text('{"file": "shelf-9.j',
                                                                                 encoding="utf-8")
    programs.started.clear()

    again = run_one(photo, tmp_path / "work", run=programs, fetch=catalogues())

    assert "error" not in again and programs.started == ["pi read"]


def test_the_summary_counts_what_the_reads_lost(tmp_path):
    photo, programs = photo_and_programs(tmp_path)
    programs.sol_answer = programs.sol_answer.replace('"readable": "no"', '"readable" "no"')  # a missing colon

    summary = run_one(photo, tmp_path / "work", run=programs, fetch=catalogues())

    assert summary["warnings"] == 1
    assert [r["read_status"] for r in rows_of(tmp_path / "work" / "shelf-9")][-1] == "unparsed"


def test_a_stage_refuses_to_write_inside_a_git_checkout(tmp_path):
    (tmp_path / ".git").mkdir()
    store_read(tmp_path / "shelf-1", "a-sol", [entry(1, "Zelený drak")])
    store_read(tmp_path / "shelf-1", "b-spark", [entry(1, "Zelený drak")])
    try:
        pipeline.merge_photo(tmp_path / "shelf-1", ["a-sol", "b-spark"])
    except ValueError as refusal:
        assert "git checkout" in str(refusal)
    else:
        raise AssertionError("merged.json was written inside a git checkout")
    assert not (tmp_path / "shelf-1" / "merged.json").exists()


# --- look-ups: cached answers, sources that are down, and the real fetcher ---


def czech_items(*titles):
    return [item(title, "cs") for title in titles]


def test_a_second_look_up_of_a_photo_asks_no_catalogue_again(tmp_path):
    store_merged(tmp_path, czech_items("Zelený drak", "Modrý pes"))
    no_czech_record = (FIXTURES / "nkcr_empty.txt").read_text(encoding="utf-8")
    asked = []

    def yaz(commands):
        asked.append(commands)
        return no_czech_record

    first = pipeline.lookup_photo(tmp_path, fetch=None, run_yaz=yaz)
    count = len(asked)
    second = pipeline.lookup_photo(tmp_path, fetch=None, run_yaz=yaz)

    assert count > 0 and len(asked) == count
    assert second == first


def test_a_catalogue_that_is_down_is_asked_once_per_photo_not_once_per_book(tmp_path):
    store_merged(tmp_path, czech_items("Zelený drak", "Modrý pes", "Bílá sova"))
    asked = []

    def yaz(commands):
        asked.append(commands)
        raise Unavailable("aleph.nkp.cz could not be reached")

    candidates = pipeline.lookup_photo(tmp_path, fetch=None, run_yaz=yaz)

    assert len(asked) == 1
    assert [[(q["step"], q["status"]) for q in book["queries"]] for book in candidates["books"]] == [
        [("title", "unavailable")], [("skipped", "unavailable")], [("skipped", "unavailable")]]


def test_a_look_up_without_an_injected_fetch_builds_the_real_one(tmp_path):
    store_merged(tmp_path, [item("鵝媽媽", "zh")])  # no catalogue for the language, so nothing is fetched

    candidates = pipeline.lookup_photo(tmp_path)

    assert candidates["books"] == [{"item": 0, "title": "鵝媽媽", "language": "zh", "queries": [], "candidates": []}]


def test_a_read_made_from_other_tiles_is_made_again(tmp_path):
    # Review council: after `hl tiles` on a retaken photo, the old reads looked current.
    photo, programs = photo_and_programs(tmp_path)
    run_one(photo, tmp_path / "work", run=programs, fetch=catalogues())
    Image.new("RGB", (640, 480), "grey").save(photo)
    cut_tiles(photo, tmp_path / "work" / "shelf-9")  # what `hl tiles` does
    programs.sol_answer = programs.spark_answer = answer(entry(1, "あかいふうせん", "ja"))
    programs.started.clear()

    run_one(photo, tmp_path / "work", run=programs, fetch=catalogues())

    assert sorted(programs.started) == ["codex pick", "codex read", "pi read"]
    assert [row["title"] for row in rows_of(tmp_path / "work" / "shelf-9")] == ["あかいふうせん"]


def test_reads_made_from_other_tiles_are_not_merged(tmp_path):
    # PR review: `hl merge` compared reads without asking which tiles they were made from.
    photo, programs = photo_and_programs(tmp_path)
    run_one(photo, tmp_path / "work", run=programs, fetch=catalogues())
    Image.new("RGB", (640, 480), "grey").save(photo)
    cut_tiles(photo, tmp_path / "work" / "shelf-9")

    with pytest.raises(ValueError, match="a-sol was made from other tiles"):
        pipeline.merge_photo(tmp_path / "work" / "shelf-9", ["a-sol", "b-spark"])


def test_force_asks_the_catalogues_again_and_a_plain_rerun_does_not(tmp_path):
    # PR review: an empty answer stayed in the look-up cache for good, even through --force.
    photo, programs = photo_and_programs(tmp_path)
    asked, answers = [], catalogues()

    def fetch(url):
        asked.append(url)
        return (FIXTURES / "loc_empty.xml").read_bytes() if "loc.gov" in url else answers(url)

    run_one(photo, tmp_path / "work", run=programs, fetch=fetch)
    once = len(asked)
    run_one(photo, tmp_path / "work", run=programs, fetch=fetch)
    assert once > 0 and len(asked) == once

    run_one(photo, tmp_path / "work", run=programs, fetch=fetch, force=True)
    assert len(asked) == 2 * once
