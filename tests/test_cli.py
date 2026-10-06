"""The hl command: each stage can be run by itself on a photo, from a shell or an agent harness."""
import csv
import json

from PIL import Image

from home_library.cli import main


def entry(n, title, language="cs", readable="yes"):
    return {"n": n, "where": "r1c1-r0.jpg", "visible": "spine", "title": title, "other_text": "",
            "language": language, "readable": readable, "confidence": "high", "inferred": ""}


def store_read(work, stem, read_id, books):
    read = {"file": stem + ".jpg", "books": books, "errors": [], "complete": True, "read_id": read_id}
    target = work / stem / "reads" / read_id
    target.mkdir(parents=True)
    (target / "read.json").write_text(json.dumps(read, ensure_ascii=False), encoding="utf-8")


def test_tiles_cuts_a_photo_into_its_work_directory(tmp_path, capsys):
    photo = tmp_path / "shelf-9.jpg"
    Image.new("RGB", (640, 480), "white").save(photo)

    code = main(["tiles", str(photo), "--work-root", str(tmp_path / "work")])

    assert code == 0
    assert sorted(p.name for p in (tmp_path / "work" / "shelf-9" / "tiles").iterdir()) == [
        "r1c1-r0.jpg", "r1c1-r180.jpg"]
    assert "2 images" in capsys.readouterr().out


def test_tiles_of_another_photo_under_the_same_name_remove_what_was_made_from_the_old_one(tmp_path):
    # PR review: `hl tiles` on a retaken photo left the old reads, and `hl merge` then merged them.
    photo, directory = tmp_path / "shelf-9.jpg", tmp_path / "work" / "shelf-9"
    Image.new("RGB", (640, 480), "white").save(photo)
    assert main(["tiles", str(photo), "--work-root", str(tmp_path / "work")]) == 0
    store_read(tmp_path / "work", "shelf-9", "a-sol", [entry(1, "Zelený drak")])
    made = [directory / name for name in ("merged.json", "records.csv", "records.json", "lookup/candidates.json")]
    for path in made:
        path.parent.mkdir(exist_ok=True)
        path.write_text("old", encoding="utf-8")

    assert main(["tiles", str(photo), "--work-root", str(tmp_path / "work")]) == 0  # the same photo: all kept
    assert (directory / "reads" / "a-sol" / "read.json").exists() and all(path.exists() for path in made)

    Image.new("RGB", (640, 480), "grey").save(photo)
    assert main(["tiles", str(photo), "--work-root", str(tmp_path / "work")]) == 0
    assert not (directory / "reads").exists() and not any(path.exists() for path in made)


def test_merge_then_export_turn_two_stored_reads_into_a_review_sheet(tmp_path):
    work = tmp_path / "work"
    store_read(work, "shelf-9", "a-sol", [entry(1, "Zelený drak"), entry(2, "The Blue Kite", "en")])
    store_read(work, "shelf-9", "b-spark", [entry(1, "Zelený drak")])

    assert main(["merge", "shelf-9.jpg", "--work-root", str(work)]) == 0
    assert main(["export", "shelf-9.jpg", "--work-root", str(work), "--location", "Shelf 2"]) == 0

    with open(work / "shelf-9" / "records.csv", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [(r["title"], r["read_status"], r["location"]) for r in rows] == [
        ("Zelený drak", "agreed", "Shelf 2"), ("The Blue Kite", "solo", "Shelf 2")]


def test_gather_prints_one_reads_answers_for_all_photos(tmp_path, capsys):
    work = tmp_path / "work"
    store_read(work, "shelf-9", "a-sol", [entry(1, "Zelený drak")])

    assert main(["gather", "a-sol", "--work-root", str(work)]) == 0

    assert json.loads(capsys.readouterr().out) == {
        "model": "a-sol", "photos": [{"file": "shelf-9.jpg", "books": [entry(1, "Zelený drak")]}]}


def test_a_photo_that_fails_is_reported_and_the_exit_code_says_so(tmp_path, capsys):
    code = main(["run", str(tmp_path / "missing.jpg"), "--work-root", str(tmp_path / "work")])

    assert code == 1
    assert "missing.jpg" in capsys.readouterr().err


def test_a_work_root_inside_a_git_checkout_is_refused(tmp_path, capsys):
    (tmp_path / ".git").mkdir()
    photo = tmp_path / "shelf-9.jpg"
    Image.new("RGB", (640, 480), "white").save(photo)

    code = main(["tiles", str(photo), "--work-root", str(tmp_path / "work")])

    assert code == 1
    assert "git checkout" in capsys.readouterr().err
    assert not (tmp_path / "work").exists()


def test_merge_takes_the_two_reads_that_are_stored_when_none_are_named(tmp_path, capsys):
    work = tmp_path / "work"
    store_read(work, "shelf-9", "a-sol", [entry(1, "Zelený drak")])
    store_read(work, "shelf-9", "b-sol", [entry(1, "Zelený drak")])  # after --second-reader codex-exec

    assert main(["merge", "shelf-9.jpg", "--work-root", str(work)]) == 0

    merged = json.loads((work / "shelf-9" / "merged.json").read_text(encoding="utf-8"))
    assert merged["reads"] == ["a-sol", "b-sol"]


def test_merge_asks_which_reads_when_more_than_two_are_stored(tmp_path, capsys):
    work = tmp_path / "work"
    for read_id in ("a-sol", "b-sol", "b-spark"):
        store_read(work, "shelf-9", read_id, [entry(1, "Zelený drak")])

    assert main(["merge", "shelf-9.jpg", "--work-root", str(work)]) == 1

    assert "--reads" in capsys.readouterr().err
    assert not (work / "shelf-9" / "merged.json").exists()
