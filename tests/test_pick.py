import json
import subprocess
from pathlib import Path

from home_library.pick import build_prompt, parse_picks, run_pick


def reading(read_id, n, title, other_text=""):
    return {"read_id": read_id, "n": n, "where": "r1c1-r0.jpg", "visible": "spine", "title": title,
            "other_text": other_text, "language": "cs", "readable": "yes", "confidence": "high", "inferred": ""}


def cand(cid, title, **over):
    c = {"id": cid, "source": cid.split(":")[0], "source_id": cid.split(":")[1], "url": "", "title": title,
         "title_reading": "", "authors": [], "publisher": "", "year": "", "isbn": "", "series": "",
         "language": "cs", "audience": "", "age_note": "", "subjects": [], "summary": ""}
    c.update(over)
    return c


def merged_and_candidates():
    merged = {"file": "shelf-1.jpg", "reads": ["a-sol", "b-spark"], "unreadable": [], "parse_errors": [],
              "items": [
                  {"status": "accepted", "reason": "agreed", "title": "Zelený drak", "language": "cs",
                   "exact": True, "readings": [reading("a-sol", 1, "Zelený drak", "Marta Novotná"),
                                               reading("b-spark", 4, "Zelený drak", "Albatros")]},
                  {"status": "review", "reason": "solo", "title": "The Blue Kite", "language": "en",
                   "exact": False, "readings": [reading("b-spark", 7, "The Blue Kite")]},
                  {"status": "review", "reason": "solo", "title": "あかいふうせん", "language": "ja",
                   "exact": False, "readings": [reading("a-sol", 9, "あかいふうせん")]},
              ]}
    candidates = {"file": "shelf-1.jpg", "books": [
        {"item": 0, "title": "Zelený drak", "language": "cs", "queries": [],
         "candidates": [cand("nkcr:cnb001", "Zelený drak", authors=["Novotná, Marta"], publisher="Albatros",
                             year="2001", isbn="9788000000001", series="Malá knihovna"),
                        cand("nkcr:cnb002", "Zelený drak a jiné pohádky")]},
        {"item": 1, "title": "The Blue Kite", "language": "en", "queries": [], "candidates": []},
        {"item": 2, "title": "あかいふうせん", "language": "ja", "queries": [],
         "candidates": [cand("ndl:000111", "あかいふうせん", title_reading="アカイ フウセン")]},
    ]}
    return merged, candidates


def test_prompt_lists_book_reading_and_candidates_and_skips_books_without_candidates():
    merged, candidates = merged_and_candidates()
    prompt = build_prompt(merged, candidates)
    assert "Zelený drak" in prompt
    assert "Marta Novotná" in prompt and "Albatros" in prompt
    assert "nkcr:cnb001" in prompt and "nkcr:cnb002" in prompt
    assert "9788000000001" in prompt and "Malá knihovna" in prompt
    assert "ndl:000111" in prompt and "アカイ フウセン" in prompt
    assert "The Blue Kite" not in prompt


def answer(*picks):
    return json.dumps({"picks": list(picks)}, ensure_ascii=False)


def test_parse_picks_reads_a_clean_answer_in_candidates_order():
    _, candidates = merged_and_candidates()
    raw = answer(
        {"item": 2, "verdict": "match", "candidate_id": "ndl:000111", "reason": "Same title."},
        {"item": 0, "verdict": "ambiguous", "candidate_id": None, "reason": "Two editions."},
    )
    assert parse_picks(raw, candidates) == {"file": "shelf-1.jpg", "picks": [
        {"item": 0, "verdict": "ambiguous", "candidate_id": None, "reason": "Two editions."},
        {"item": 2, "verdict": "match", "candidate_id": "ndl:000111", "reason": "Same title."},
    ]}


def test_parse_picks_finds_the_object_in_a_fence_with_prose_around_it():
    _, candidates = merged_and_candidates()
    raw = ("Here is my answer.\n```json\n"
           + answer({"item": 0, "verdict": "match", "candidate_id": "nkcr:cnb001", "reason": "Same."},
                    {"item": 2, "verdict": "none", "candidate_id": None, "reason": "Different."})
           + "\n```\nHope that helps {really}.")
    picks = parse_picks(raw, candidates)["picks"]
    assert [(p["item"], p["verdict"], p["candidate_id"]) for p in picks] == [
        (0, "match", "nkcr:cnb001"), (2, "none", None)]


def test_parse_picks_rejects_a_match_naming_another_books_candidate():
    _, candidates = merged_and_candidates()
    raw = answer({"item": 0, "verdict": "match", "candidate_id": "ndl:000111", "reason": "Looks right."},
                 {"item": 2, "verdict": "match", "candidate_id": "ndl:000111", "reason": "Same title."})
    first, second = parse_picks(raw, candidates)["picks"]
    assert first["verdict"] == "none" and first["candidate_id"] is None
    assert "rejected" in first["reason"] and "ndl:000111" in first["reason"]
    assert second["verdict"] == "match"


def test_parse_picks_gives_none_for_a_book_the_answer_skips_and_ignores_unknown_items():
    _, candidates = merged_and_candidates()
    raw = answer({"item": 2, "verdict": "match", "candidate_id": "ndl:000111", "reason": "Same."},
                 {"item": 1, "verdict": "match", "candidate_id": "x:1", "reason": "No candidates here."})
    picks = parse_picks(raw, candidates)["picks"]
    assert [p["item"] for p in picks] == [0, 2]
    assert picks[0]["verdict"] == "none" and picks[0]["candidate_id"] is None
    assert picks[0]["reason"] != ""


def test_parse_picks_turns_unknown_verdict_and_non_object_pick_into_none():
    _, candidates = merged_and_candidates()
    raw = json.dumps({"picks": [{"item": 0, "verdict": "probably", "candidate_id": "nkcr:cnb001", "reason": 5},
                                "item 2 is fine"]})
    first, second = parse_picks(raw, candidates)["picks"]
    assert first["verdict"] == "none" and first["candidate_id"] is None
    assert "probably" in first["reason"]
    assert second == {"item": 2, "verdict": "none", "candidate_id": None,
                      "reason": second["reason"]} and second["reason"]


def test_parse_picks_drops_candidate_id_unless_the_verdict_is_match():
    _, candidates = merged_and_candidates()
    raw = answer({"item": 0, "verdict": "ambiguous", "candidate_id": "nkcr:cnb001", "reason": "Editions."},
                 {"item": 2, "verdict": "none", "candidate_id": "ndl:000111", "reason": "No."})
    assert [p["candidate_id"] for p in parse_picks(raw, candidates)["picks"]] == [None, None]


def test_parse_picks_gives_none_for_every_book_when_the_answer_cannot_be_read():
    _, candidates = merged_and_candidates()
    for raw in ["I cannot do this.", "", '{"picks": "none"}', '{"picks": [{"item": 0, "verdi', "[1, 2]",
                '{"picks": [{"item": [1], "verdict": "match"}]}']:
        result = parse_picks(raw, candidates)
        assert result["file"] == "shelf-1.jpg"
        assert [(p["item"], p["verdict"], p["candidate_id"]) for p in result["picks"]] == [
            (0, "none", None), (2, "none", None)]
        assert all(isinstance(p["reason"], str) and p["reason"] for p in result["picks"])


def photo_dir_with_lookup(tmp_path, candidates=None):
    merged, default = merged_and_candidates()
    (tmp_path / "lookup").mkdir()
    (tmp_path / "merged.json").write_text(json.dumps(merged, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "lookup" / "candidates.json").write_text(
        json.dumps(candidates or default, ensure_ascii=False), encoding="utf-8")
    return tmp_path


class FakeCodex:
    def __init__(self, reply=None, returncode=0, error=None):
        self.reply, self.returncode, self.error, self.calls = reply, returncode, error, []

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        if self.error:
            raise self.error
        if self.reply is not None:
            Path(args[args.index("-o") + 1]).write_text(self.reply, encoding="utf-8")
        return subprocess.CompletedProcess(args, self.returncode, "", "boom")


def test_run_pick_calls_no_model_when_no_book_has_candidates(tmp_path):
    _, candidates = merged_and_candidates()
    for book in candidates["books"]:
        book["candidates"] = []
    photo = photo_dir_with_lookup(tmp_path, candidates)
    fake = FakeCodex()
    result = run_pick(photo, run=fake)
    assert fake.calls == []
    assert result == {"file": "shelf-1.jpg", "picks": []}
    assert json.loads((photo / "lookup" / "picks.json").read_text(encoding="utf-8")) == result


def test_run_pick_runs_codex_once_in_the_lookup_directory_with_the_prompt_on_stdin(tmp_path):
    photo = photo_dir_with_lookup(tmp_path)
    merged, candidates = merged_and_candidates()
    lookup = str(photo / "lookup")
    fake = FakeCodex(reply=answer({"item": 0, "verdict": "none", "candidate_id": None, "reason": "-"}))
    run_pick(photo, run=fake, timeout=42)
    (args, kwargs), = fake.calls
    assert args == ["codex", "exec", "--ignore-user-config", "-m", "gpt-6.1-sol",
                    "-c", 'model_reasoning_effort="low"', "-s", "read-only", "--skip-git-repo-check",
                    "--ephemeral", "-C", lookup, "-o", lookup + "/picks.raw.txt", "-"]
    assert kwargs["cwd"] == lookup
    assert kwargs["input"] == build_prompt(merged, candidates)
    assert kwargs["timeout"] == 42


def test_run_pick_writes_picks_json_from_the_answer_file(tmp_path):
    photo = photo_dir_with_lookup(tmp_path)
    reply = answer({"item": 0, "verdict": "match", "candidate_id": "nkcr:cnb001", "reason": "Same title."},
                   {"item": 2, "verdict": "none", "candidate_id": None, "reason": "Different book."})
    result = run_pick(photo, run=FakeCodex(reply=reply))
    assert [p["verdict"] for p in result["picks"]] == ["match", "none"]
    text = (photo / "lookup" / "picks.json").read_text(encoding="utf-8")
    assert text.endswith("}\n") and '\n  "picks": [' in text
    assert json.loads(text) == result


def test_a_failing_model_call_gives_none_for_every_book_with_the_reason(tmp_path):
    cases = [
        (FakeCodex(returncode=2), "exit"),
        (FakeCodex(error=subprocess.TimeoutExpired("codex", 300)), "timed out"),
        (FakeCodex(error=FileNotFoundError("codex")), "not found"),
        (FakeCodex(), "no answer"),
    ]
    for fake, why in cases:
        directory = tmp_path / why.replace(" ", "-")
        directory.mkdir()
        photo = photo_dir_with_lookup(directory)
        result = run_pick(photo, run=fake)
        assert [(p["item"], p["verdict"], p["candidate_id"]) for p in result["picks"]] == [
            (0, "none", None), (2, "none", None)]
        assert all("pick step failed" in p["reason"] and why in p["reason"] for p in result["picks"])
        assert json.loads((photo / "lookup" / "picks.json").read_text(encoding="utf-8")) == result


def test_a_stale_answer_file_is_not_taken_for_this_runs_answer(tmp_path):
    photo = photo_dir_with_lookup(tmp_path)
    (photo / "lookup" / "picks.raw.txt").write_text(
        answer({"item": 0, "verdict": "match", "candidate_id": "nkcr:cnb001", "reason": "Old."}),
        encoding="utf-8")
    result = run_pick(photo, run=FakeCodex())
    assert [p["verdict"] for p in result["picks"]] == ["none", "none"]


def test_parse_picks_rejects_a_match_whose_candidate_id_is_not_a_string():
    _, candidates = merged_and_candidates()
    for bad in ([], {}, 7, ["nkcr:cnb001"]):
        raw = answer({"item": 0, "verdict": "match", "candidate_id": bad, "reason": "x"},
                     {"item": 2, "verdict": "match", "candidate_id": "ndl:000111", "reason": "Same."})
        picks = parse_picks(raw, candidates)["picks"]
        assert [(p["verdict"], p["candidate_id"]) for p in picks] == [("none", None), ("match", "ndl:000111")]
        assert "rejected" in picks[0]["reason"]


def test_parse_picks_gives_none_for_every_book_when_the_answer_nests_too_deeply():
    _, candidates = merged_and_candidates()
    raw = '{"picks":' + "[" * 1100 + "0" + "]" * 1100 + "}"
    picks = parse_picks(raw, candidates)["picks"]
    assert [(p["item"], p["verdict"]) for p in picks] == [(0, "none"), (2, "none")]


def test_run_pick_given_a_relative_photo_directory_passes_absolute_paths_to_codex(tmp_path, monkeypatch):
    (tmp_path / "shelf-1").mkdir()
    photo_dir_with_lookup(tmp_path / "shelf-1")
    monkeypatch.chdir(tmp_path)
    fake = FakeCodex(reply=answer())
    run_pick("shelf-1", run=fake)
    (args, kwargs), = fake.calls
    lookup = str((tmp_path / "shelf-1" / "lookup").resolve())
    assert args[args.index("-C") + 1] == lookup
    assert args[args.index("-o") + 1] == lookup + "/picks.raw.txt"
    assert kwargs["cwd"] == lookup
