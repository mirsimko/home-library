import json

from home_library.parse import parse_read

FIELDS = ["n", "where", "visible", "title", "other_text", "language", "readable", "confidence", "inferred"]


def entry(n=1, title="Zelený drak", **over):
    e = {"n": n, "where": "r1c1-r0.jpg, left", "visible": "spine", "title": title, "other_text": "",
         "language": "cs", "readable": "yes", "confidence": "high", "inferred": ""}
    e.update(over)
    return e


def answer(*entries, file="shelf-1.jpg"):
    return json.dumps({"file": file, "books": list(entries)}, ensure_ascii=False)


def test_clean_json_answer_gives_complete_read():
    raw = answer(entry(1, "Zelený drak"), entry(2, "あかいふうせん", language="ja"))
    read = parse_read(raw)
    assert read["file"] == "shelf-1.jpg"
    assert [b["title"] for b in read["books"]] == ["Zelený drak", "あかいふうせん"]
    assert read["errors"] == []
    assert read["complete"] is True


def test_answer_in_code_fence_with_prose_is_read():
    raw = "Here are the books I found:\n```json\n" + answer(entry(1, "The Blue Kite", language="en")) + "\n```\nHope this helps!"
    read = parse_read(raw)
    assert [b["title"] for b in read["books"]] == ["The Blue Kite"]
    assert read["file"] == "shelf-1.jpg"
    assert read["complete"] is True
