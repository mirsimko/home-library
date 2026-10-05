import json
import subprocess

from home_library.pick import build_prompt, parse_picks


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
