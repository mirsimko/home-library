import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from PIL import Image

from home_library.reader import BACKENDS, ReadError, render_prompt, run_read
from home_library.tiles import cut_tiles

SIX_TILE_FILES = (
    "r1c1-r0.jpg r1c1-r180.jpg r1c2-r0.jpg r1c2-r180.jpg r1c3-r0.jpg r1c3-r180.jpg "
    "r2c1-r0.jpg r2c1-r180.jpg r2c2-r0.jpg r2c2-r180.jpg r2c3-r0.jpg r2c3-r180.jpg"
)


def cut_small_photo(tmp_path, name="shelf-1.jpg"):
    """A 250x150 photo cut into 100x100 tiles: 2 rows by 3 columns."""
    photo = tmp_path / name
    Image.new("RGB", (250, 150), (200, 120, 40)).save(photo, "JPEG")
    work = tmp_path / "work" / photo.stem
    manifest = cut_tiles(photo, work, tile_width=100, tile_height=100,
                         min_overlap_x=20, min_overlap_y=20)
    return work, manifest


def test_prompt_for_a_two_by_three_manifest_names_every_tile_and_the_counts(tmp_path):
    _, manifest = cut_small_photo(tmp_path)

    prompt = render_prompt(manifest)

    assert f"The images are attached in this order: {SIX_TILE_FILES}\n" in prompt
    assert "Attached are 12 images: the photo cut into 6 overlapping tiles" in prompt
    assert "(2 rows by 3 columns)" in prompt
    assert '{"file": "shelf-1.jpg", "books": [' in prompt
    assert "<<" not in prompt


ANSWER = json.dumps(
    {"file": "shelf-1.jpg", "books": [
        {"n": 1, "where": "r1c1-r0.jpg, left", "visible": "spine", "title": "Zelený drak", "other_text": "",
         "language": "cs", "readable": "yes", "confidence": "high", "inferred": ""}]},
    ensure_ascii=False)


def codex_stream(answer=ANSWER, *, extra=(), usage=None):
    events = [{"type": "thread.started", "thread_id": "t-1"}, {"type": "turn.started"}, *extra,
              {"type": "item.completed", "item": {"id": "item_9", "type": "agent_message", "text": answer}},
              {"type": "turn.completed",
               "usage": usage or {"input_tokens": 100, "cached_input_tokens": 10, "output_tokens": 5}}]
    return "".join(json.dumps(event) + "\n" for event in events)


class FakeRun:
    """Stands in for subprocess.run: records each call and returns a canned result."""

    def __init__(self, stdout="", returncode=0, stderr="", raises=None):
        self.calls = []
        self.result = SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)
        self.raises = raises

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        if self.raises:
            raise self.raises
        return self.result


def test_codex_exec_runs_in_the_tiles_directory_with_the_prompt_on_standard_input(tmp_path):
    work, manifest = cut_small_photo(tmp_path)
    run = FakeRun(stdout=codex_stream())

    run_read(work, "a-sol", "codex-exec", run=run)

    (args, kwargs), = run.calls
    assert args == [
        "codex", "exec", "--ignore-user-config", "-m", "gpt-6.1-sol", "-c", 'model_reasoning_effort="low"',
        "-s", "read-only", "--skip-git-repo-check", "--ephemeral", "-C", str(work / "tiles"),
        "-i", ",".join(SIX_TILE_FILES.split()), "--json", "-"]
    assert kwargs["cwd"] == work / "tiles"
    assert kwargs["input"] == render_prompt(manifest)
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["encoding"] == "utf-8"
    assert kwargs["timeout"] == 600
    assert (work / "reads" / "a-sol" / "prompt.txt").read_text(encoding="utf-8") == render_prompt(manifest)


def test_codex_answer_comes_from_the_last_agent_message_and_the_stream_is_kept(tmp_path):
    work, _ = cut_small_photo(tmp_path)
    early = {"type": "item.completed", "item": {"id": "item_1", "type": "agent_message", "text": "Looking now."}}
    reasoning = {"type": "item.completed", "item": {"id": "item_0", "type": "reasoning", "text": "hmm"}}
    stdout = "\n" + codex_stream(extra=[reasoning, early]) + "  \n"  # blank lines are not events
    run = FakeRun(stdout=stdout)

    run_read(work, "a-sol", "codex-exec", run=run)

    read_dir = work / "reads" / "a-sol"
    assert (read_dir / "raw.txt").read_text(encoding="utf-8") == ANSWER
    assert (read_dir / "events.jsonl").read_text(encoding="utf-8") == stdout


def test_read_json_holds_the_parsed_books_and_the_read_id(tmp_path):
    work, _ = cut_small_photo(tmp_path)
    run = FakeRun(stdout=codex_stream())

    read = run_read(work, "a-sol", "codex-exec", run=run)

    text = (work / "reads" / "a-sol" / "read.json").read_text(encoding="utf-8")
    assert json.loads(text) == read
    assert "Zelený drak" in text
    assert text.endswith("}\n")
    assert read["read_id"] == "a-sol"
    assert read["file"] == "shelf-1.jpg"
    assert read["complete"] is True
    assert read["errors"] == []
    assert [(b["n"], b["title"], b["language"]) for b in read["books"]] == [(1, "Zelený drak", "cs")]


def test_an_empty_file_in_the_answer_is_filled_with_the_photo_name(tmp_path):
    work, _ = cut_small_photo(tmp_path)
    answer = json.dumps({"file": "", "books": []})
    run = FakeRun(stdout=codex_stream(answer))

    read = run_read(work, "a-sol", "codex-exec", run=run)

    assert read["file"] == "shelf-1.jpg"
    stored = json.loads((work / "reads" / "a-sol" / "read.json").read_text(encoding="utf-8"))
    assert stored["file"] == "shelf-1.jpg"


def fixed_clock(*readings):
    values = iter(readings)
    return lambda: next(values)


def test_run_json_records_how_the_codex_read_was_run(tmp_path):
    work, _ = cut_small_photo(tmp_path)
    run = FakeRun(stdout=codex_stream(usage={"input_tokens": 19989, "cached_input_tokens": 7168,
                                             "output_tokens": 5}))
    start = datetime(2026, 10, 5, 19, 40, 1, tzinfo=timezone(timedelta(hours=9)))

    run_read(work, "a-sol", "codex-exec", run=run, clock=fixed_clock(1000.0, 1113.25), now=lambda: start)

    info = json.loads((work / "reads" / "a-sol" / "run.json").read_text(encoding="utf-8"))
    assert info == {
        "read_id": "a-sol",
        "backend": "codex-exec",
        "model": "gpt-6.1-sol",
        "command": run.calls[0][0],
        "started": "2026-10-05T19:40:01+09:00",
        "seconds": 113.25,
        "returncode": 0,
        "tool_calls": [],
        "usage": {"input_tokens": 19989, "cached_input_tokens": 7168, "output_tokens": 5},
    }


def test_a_codex_stream_without_turn_completed_fails_the_read_and_leaves_usage_null(tmp_path):
    work, _ = cut_small_photo(tmp_path)
    message = {"type": "item.completed", "item": {"id": "item_0", "type": "agent_message", "text": ANSWER}}
    stdout = json.dumps(message) + "\n"
    run = FakeRun(stdout=stdout)

    with pytest.raises(ReadError, match="turn.completed"):
        run_read(work, "a-sol", "codex-exec", run=run)

    read_dir = read_dir_of(work, "a-sol")
    assert not (read_dir / "read.json").exists()
    assert (read_dir / "raw.txt").read_text(encoding="utf-8") == ANSWER
    assert (read_dir / "events.jsonl").read_text(encoding="utf-8") == stdout
    assert json.loads((read_dir / "run.json").read_text(encoding="utf-8"))["usage"] is None


def test_a_codex_read_that_ran_a_command_is_rejected_and_leaves_no_read_json(tmp_path):
    work, _ = cut_small_photo(tmp_path)
    command = {"id": "item_1", "type": "command_execution", "command": "ls", "status": "in_progress"}
    done = {**command, "status": "completed", "exit_code": 0}
    extra = [{"type": "item.started", "item": command}, {"type": "item.completed", "item": done}]
    run = FakeRun(stdout=codex_stream(extra=extra))

    with pytest.raises(ReadError, match="used tools"):
        run_read(work, "a-sol", "codex-exec", run=run)

    read_dir = work / "reads" / "a-sol"
    assert not (read_dir / "read.json").exists()
    assert (read_dir / "raw.txt").read_text(encoding="utf-8") == ANSWER
    assert json.loads((read_dir / "run.json").read_text(encoding="utf-8"))["tool_calls"] == ["command_execution"]


def test_pi_gets_each_tile_as_an_argument_and_the_prompt_last_and_answers_on_stdout(tmp_path):
    work, manifest = cut_small_photo(tmp_path)
    run = FakeRun(stdout=ANSWER)

    read = run_read(work, "b-spark", "pi", run=run)

    prompt = render_prompt(manifest)
    (args, kwargs), = run.calls
    assert args == [
        "pi", "-p", "--model", "opencode-go/muse-spark-1.3-contributor", "--thinking", "medium",
        "--no-context-files", "--no-skills", "--no-prompt-templates", "--no-extensions", "--no-tools",
        "--no-session", *[f"@{name}" for name in SIX_TILE_FILES.split()], prompt]
    assert kwargs["cwd"] == work / "tiles"
    assert read["read_id"] == "b-spark"
    assert [b["title"] for b in read["books"]] == ["Zelený drak"]
    read_dir = work / "reads" / "b-spark"
    assert (read_dir / "prompt.txt").read_text(encoding="utf-8") == prompt
    assert (read_dir / "raw.txt").read_text(encoding="utf-8") == ANSWER
    assert not (read_dir / "events.jsonl").exists()
    info = json.loads((read_dir / "run.json").read_text(encoding="utf-8"))
    assert info["backend"] == "pi"
    assert info["model"] == "opencode-go/muse-spark-1.3-contributor"
    assert info["command"] == [*args[:-1], "<prompt>"]
    assert info["tool_calls"] == []
    assert info["usage"] is None


def test_pi_runs_with_standard_input_closed(tmp_path):
    # With an image attached, pi waits for standard input to end; left open, the read hangs until the timeout.
    work, _ = cut_small_photo(tmp_path)
    run = FakeRun(stdout=ANSWER)

    run_read(work, "b-spark", "pi", run=run)

    (_, kwargs), = run.calls
    assert kwargs["input"] == ""


def test_a_failed_run_reports_what_the_program_printed_on_standard_error(tmp_path):
    work, _ = cut_small_photo(tmp_path)
    run = FakeRun(stdout="", returncode=1, stderr="No API key found for opencode-go\n")

    with pytest.raises(ReadError, match="No API key found for opencode-go"):
        run_read(work, "b-spark", "pi", run=run)


def read_dir_of(work, read_id):
    return work / "reads" / read_id


def test_a_non_zero_return_code_is_an_error_that_keeps_raw_and_run_json(tmp_path):
    work, _ = cut_small_photo(tmp_path)
    run = FakeRun(stdout=ANSWER, returncode=2, stderr="boom")

    with pytest.raises(ReadError, match="return code 2"):
        run_read(work, "b-spark", "pi", run=run)

    read_dir = read_dir_of(work, "b-spark")
    assert not (read_dir / "read.json").exists()
    assert (read_dir / "raw.txt").read_text(encoding="utf-8") == ANSWER
    assert json.loads((read_dir / "run.json").read_text(encoding="utf-8"))["returncode"] == 2


def test_a_timeout_is_an_error_with_a_null_return_code(tmp_path):
    work, _ = cut_small_photo(tmp_path)
    run = FakeRun(raises=subprocess.TimeoutExpired(cmd="pi", timeout=600))

    with pytest.raises(ReadError, match="timed out after 600"):
        run_read(work, "b-spark", "pi", run=run, clock=fixed_clock(5.0, 605.0))

    read_dir = read_dir_of(work, "b-spark")
    assert not (read_dir / "read.json").exists()
    assert (read_dir / "raw.txt").read_text(encoding="utf-8") == ""
    info = json.loads((read_dir / "run.json").read_text(encoding="utf-8"))
    assert info["returncode"] is None
    assert info["seconds"] == 600.0


def test_a_program_that_is_not_installed_is_an_error_that_keeps_run_json(tmp_path):
    work, _ = cut_small_photo(tmp_path)
    run = FakeRun(raises=FileNotFoundError(2, "No such file or directory: 'codex'"))

    with pytest.raises(ReadError, match="codex is not installed"):
        run_read(work, "a-sol", "codex-exec", run=run)

    read_dir = read_dir_of(work, "a-sol")
    assert not (read_dir / "read.json").exists()
    assert (read_dir / "raw.txt").read_text(encoding="utf-8") == ""
    assert json.loads((read_dir / "run.json").read_text(encoding="utf-8"))["returncode"] is None


def test_an_empty_answer_is_an_error_that_keeps_raw_and_run_json(tmp_path):
    work, _ = cut_small_photo(tmp_path)
    run = FakeRun(stdout="  \n")

    with pytest.raises(ReadError, match="empty answer"):
        run_read(work, "b-spark", "pi", run=run)

    read_dir = read_dir_of(work, "b-spark")
    assert not (read_dir / "read.json").exists()
    assert (read_dir / "raw.txt").read_text(encoding="utf-8") == "  \n"
    assert json.loads((read_dir / "run.json").read_text(encoding="utf-8"))["returncode"] == 0


def test_a_codex_stream_without_an_answer_is_an_error(tmp_path):
    work, _ = cut_small_photo(tmp_path)
    run = FakeRun(stdout='{"type": "turn.started"}\n')

    with pytest.raises(ReadError, match="empty answer"):
        run_read(work, "a-sol", "codex-exec", run=run)

    assert not (read_dir_of(work, "a-sol") / "read.json").exists()


def test_an_extra_file_in_tiles_is_refused_before_anything_runs(tmp_path):
    work, _ = cut_small_photo(tmp_path)
    (work / "tiles" / "notes.txt").write_text("not a tile", encoding="utf-8")
    run = FakeRun(stdout=ANSWER)

    with pytest.raises(ReadError, match="notes.txt"):
        run_read(work, "b-spark", "pi", run=run)

    assert run.calls == []
    assert not (work / "reads").exists()


def test_a_missing_tile_is_refused_before_anything_runs(tmp_path):
    work, _ = cut_small_photo(tmp_path)
    (work / "tiles" / "r2c3-r180.jpg").unlink()
    run = FakeRun(stdout=ANSWER)

    with pytest.raises(ReadError, match="r2c3-r180.jpg"):
        run_read(work, "b-spark", "pi", run=run)

    assert run.calls == []
    assert not (work / "reads").exists()


def test_a_failed_run_removes_the_read_json_of_an_earlier_run_of_the_same_read(tmp_path):
    work, _ = cut_small_photo(tmp_path)
    run_read(work, "b-spark", "pi", run=FakeRun(stdout=ANSWER))
    assert (read_dir_of(work, "b-spark") / "read.json").exists()

    with pytest.raises(ReadError):
        run_read(work, "b-spark", "pi", run=FakeRun(stdout="", returncode=1))

    assert not (read_dir_of(work, "b-spark") / "read.json").exists()


def test_an_unknown_backend_is_refused_before_anything_runs(tmp_path):
    work, _ = cut_small_photo(tmp_path)
    run = FakeRun(stdout=ANSWER)

    with pytest.raises(ReadError, match="unknown backend 'gemini'"):
        run_read(work, "x-gemini", "gemini", run=run)

    assert run.calls == []
    assert not (work / "reads").exists()


def test_the_backends_have_their_default_models():
    assert BACKENDS == {"codex-exec": "gpt-6.1-sol", "pi": "opencode-go/muse-spark-1.3-contributor"}


def test_a_relative_work_directory_gives_codex_an_absolute_tiles_directory(tmp_path, monkeypatch):
    work, _ = cut_small_photo(tmp_path)
    monkeypatch.chdir(tmp_path)
    run = FakeRun(stdout=codex_stream())

    run_read(Path("work") / "shelf-1", "a-sol", "codex-exec", run=run)

    (args, kwargs), = run.calls
    tiles = (work / "tiles").resolve()
    assert args[args.index("-C") + 1] == str(tiles)
    assert kwargs["cwd"] == tiles


@pytest.mark.parametrize("damage", ["extra", "missing"])
def test_a_refused_retry_removes_the_read_json_of_an_earlier_run(tmp_path, damage):
    work, _ = cut_small_photo(tmp_path)
    run_read(work, "b-spark", "pi", run=FakeRun(stdout=ANSWER))
    if damage == "extra":
        (work / "tiles" / "notes.txt").write_text("not a tile", encoding="utf-8")
    else:
        (work / "tiles" / "r2c3-r180.jpg").unlink()

    with pytest.raises(ReadError):
        run_read(work, "b-spark", "pi", run=FakeRun(stdout=ANSWER))

    assert not (read_dir_of(work, "b-spark") / "read.json").exists()


def test_a_retry_with_an_unknown_backend_removes_the_read_json_of_an_earlier_run(tmp_path):
    work, _ = cut_small_photo(tmp_path)
    run_read(work, "b-spark", "pi", run=FakeRun(stdout=ANSWER))

    with pytest.raises(ReadError, match="unknown backend"):
        run_read(work, "b-spark", "gemini", run=FakeRun(stdout=ANSWER))

    assert not (read_dir_of(work, "b-spark") / "read.json").exists()


def test_pi_rerun_of_a_codex_read_leaves_no_event_stream(tmp_path):
    work, _ = cut_small_photo(tmp_path)
    run_read(work, "a-sol", "codex-exec", run=FakeRun(stdout=codex_stream()))
    assert (read_dir_of(work, "a-sol") / "events.jsonl").exists()

    run_read(work, "a-sol", "pi", run=FakeRun(stdout=ANSWER))

    assert not (read_dir_of(work, "a-sol") / "events.jsonl").exists()


@pytest.mark.parametrize("replacement", ["directory", "broken-link"])
def test_a_listed_tile_that_is_not_a_file_is_refused_before_anything_runs(tmp_path, replacement):
    work, _ = cut_small_photo(tmp_path)
    tile = work / "tiles" / "r1c2-r0.jpg"
    tile.unlink()
    if replacement == "directory":
        tile.mkdir()
    else:
        tile.symlink_to(tmp_path / "nowhere.jpg")
    run = FakeRun(stdout=ANSWER)

    with pytest.raises(ReadError, match="r1c2-r0.jpg"):
        run_read(work, "b-spark", "pi", run=run)

    assert run.calls == []


def test_a_timeout_keeps_the_partial_stream_and_its_answer_and_tool_calls(tmp_path):
    work, _ = cut_small_photo(tmp_path)
    command = {"id": "item_1", "type": "command_execution", "command": "ls", "status": "in_progress"}
    partial = codex_stream(extra=[{"type": "item.started", "item": command}])
    run = FakeRun(raises=subprocess.TimeoutExpired(cmd="codex", timeout=600, output=partial.encode("utf-8")))

    with pytest.raises(ReadError, match="timed out after 600"):
        run_read(work, "a-sol", "codex-exec", run=run)

    read_dir = read_dir_of(work, "a-sol")
    assert (read_dir / "events.jsonl").read_text(encoding="utf-8") == partial
    assert (read_dir / "raw.txt").read_text(encoding="utf-8") == ANSWER
    info = json.loads((read_dir / "run.json").read_text(encoding="utf-8"))
    assert info["returncode"] is None
    assert info["tool_calls"] == ["command_execution"]
    assert not (read_dir / "read.json").exists()


def test_a_work_directory_inside_a_git_checkout_is_refused_before_anything_is_written(tmp_path):
    work, _ = cut_small_photo(tmp_path)
    repo_work = tmp_path / "repo" / "work" / "shelf-1"
    shutil.copytree(work, repo_work)
    (tmp_path / "repo" / ".git").mkdir()
    run = FakeRun(stdout=ANSWER)

    with pytest.raises(ReadError, match="git checkout"):
        run_read(repo_work, "b-spark", "pi", run=run)

    assert run.calls == []
    assert not (repo_work / "reads").exists()


def started_and_done(item_id, kind, **fields):
    item = {"id": item_id, "type": kind, **fields}
    return [{"type": "item.started", "item": item}, {"type": "item.completed", "item": item}]


@pytest.mark.parametrize("extra, expected", [
    ([{"type": "item.started", "item": {"id": "item_1", "type": "command_execution", "command": "ls"}}],
     ["command_execution"]),
    (started_and_done("item_1", "web_search", query="x"), ["web_search"]),
    (started_and_done("item_1", "command_execution") + started_and_done("item_2", "command_execution"),
     ["command_execution", "command_execution"]),
    (started_and_done("item_1", "mcp_tool_call") + started_and_done("item_2", "command_execution"),
     ["mcp_tool_call", "command_execution"]),
])
def test_every_distinct_tool_item_is_listed_and_rejects_the_read(tmp_path, extra, expected):
    work, _ = cut_small_photo(tmp_path)
    run = FakeRun(stdout=codex_stream(extra=extra))

    with pytest.raises(ReadError, match="used tools"):
        run_read(work, "a-sol", "codex-exec", run=run)

    info = json.loads((read_dir_of(work, "a-sol") / "run.json").read_text(encoding="utf-8"))
    assert info["tool_calls"] == expected
    assert not (read_dir_of(work, "a-sol") / "read.json").exists()


def reversed_manifest(work):
    manifest = json.loads((work / "tiles.json").read_text(encoding="utf-8"))
    manifest["tiles"].reverse()
    (work / "tiles.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def test_the_prompt_and_both_commands_keep_the_manifest_order(tmp_path):
    work, _ = cut_small_photo(tmp_path)
    manifest = reversed_manifest(work)
    names = SIX_TILE_FILES.split()[::-1]

    assert f"in this order: {' '.join(names)}\n" in render_prompt(manifest)
    codex, pi = FakeRun(stdout=codex_stream()), FakeRun(stdout=ANSWER)
    run_read(work, "a-sol", "codex-exec", run=codex)
    run_read(work, "b-spark", "pi", run=pi)

    codex_args = codex.calls[0][0]
    assert codex_args[codex_args.index("-i") + 1] == ",".join(names)
    assert pi.calls[0][0][12:-1] == [f"@{name}" for name in names]


EXPECTED_PROMPT = """You are reading book titles from one photo of a family's bookshelves. The books are children's books in Japanese, Czech and English.

Attached are 12 images: the photo cut into 6 overlapping tiles at full resolution (2 rows by 3 columns), each tile given twice. A name such as r1c2 means row 1 from the top, column 2 from the left. Files ending in -r0 show the tile as photographed. Files ending in -r180 show the same tile turned by 180 degrees, so that text on upside-down books can be read upright. Neighbouring tiles overlap, so the same book can appear in several images.

The images are attached in this order: """ + SIX_TILE_FILES + """

Rules:
- Read with your own vision, from these 12 images only. Use no tools, no OCR and no look-ups. Do not run any command and do not open any file.
- Do not stop to ask a question. Everything you need is attached.
- List every distinct physical book once, including books you cannot read. Count a run of unreadable thin books as one entry and say roughly how many there are.
- Write each title exactly as printed, in its original script, with Czech diacritics. Put only the title in "title". A publisher, imprint, author, series name or issue number goes in "other_text".
- Do not complete a title from memory and do not guess. If part of a title is not legible, put only the legible part in "title", mark the entry partial, and put any guess in "inferred". Never write placeholder words in "title".

Answer with one JSON object and nothing else, in this shape:

{"file": "shelf-1.jpg", "books": [{"n": 1, "where": "<tile name and where in it>", "visible": "spine | front cover | back cover | edge", "title": "<as printed, or empty>", "other_text": "<everything else legible>", "language": "ja | cs | en | zh | unknown", "readable": "yes | partial | no", "confidence": "high | medium | low", "inferred": "<a guess, or empty>"}]}
"""


def test_the_rendered_prompt_is_the_exact_text_of_the_contract(tmp_path):
    _, manifest = cut_small_photo(tmp_path)

    assert render_prompt(manifest).rstrip("\n") == EXPECTED_PROMPT.rstrip("\n")


def test_a_read_is_stored_under_the_photos_own_name_whatever_the_model_wrote(tmp_path):
    work, manifest = cut_small_photo(tmp_path)
    wrong_name = json.dumps({"file": "another-photo.jpg", "books": []})

    read = run_read(work, "b-spark", "pi", run=FakeRun(stdout=wrong_name))

    assert read["file"] == manifest["photo"] != "another-photo.jpg"


@pytest.mark.parametrize("read_id", ["ELSEWHERE", "../escape", "a/b", "a..b/c", "..", ".hidden", "-x", "", "a b"])
def test_a_read_id_that_is_not_a_plain_name_is_refused_before_anything_is_written(tmp_path, read_id):
    work, _ = cut_small_photo(tmp_path)
    if read_id == "ELSEWHERE":
        read_id = str(tmp_path / "place")  # an absolute path replaces the reads directory when joined
    run_read(work, "a-sol", "pi", run=FakeRun(stdout=ANSWER))
    run = FakeRun(stdout=ANSWER)

    with pytest.raises(ReadError, match="read id"):
        run_read(work, read_id, "pi", run=run)

    assert run.calls == []
    assert (read_dir_of(work, "a-sol") / "read.json").exists()
    assert sorted(path.name for path in (work / "reads").iterdir()) == ["a-sol"]
    assert not (tmp_path / "place").exists()
    assert not (work / "escape").exists()


def test_a_read_id_with_dots_and_dashes_inside_a_plain_name_is_accepted(tmp_path):
    work, _ = cut_small_photo(tmp_path)

    read = run_read(work, "b-spark_2.v1", "pi", run=FakeRun(stdout=ANSWER))

    assert read["read_id"] == "b-spark_2.v1"


def test_read_json_records_the_hash_of_the_tiles_manifest_the_read_was_made_from(tmp_path):
    work, _ = cut_small_photo(tmp_path)
    manifest_bytes = (work / "tiles.json").read_bytes()

    read = run_read(work, "b-spark", "pi", run=FakeRun(stdout=ANSWER))

    expected = hashlib.sha256(manifest_bytes).hexdigest()
    assert len(expected) == 64
    assert read["photo_sha256"] == expected
    stored = json.loads((read_dir_of(work, "b-spark") / "read.json").read_text(encoding="utf-8"))
    assert stored["photo_sha256"] == expected


@pytest.mark.parametrize("answer", [
    "Error: 429 rate limit exceeded, try again later.",
    '{"file": "shelf-1.jpg", "result": []}',
])
def test_an_answer_with_no_books_list_is_a_failed_read_that_keeps_raw_and_run_json(tmp_path, answer):
    work, _ = cut_small_photo(tmp_path)
    run = FakeRun(stdout=answer)

    with pytest.raises(ReadError, match="no books list"):
        run_read(work, "b-spark", "pi", run=run)

    read_dir = read_dir_of(work, "b-spark")
    assert not (read_dir / "read.json").exists()
    assert (read_dir / "raw.txt").read_text(encoding="utf-8") == answer
    assert json.loads((read_dir / "run.json").read_text(encoding="utf-8"))["returncode"] == 0


def test_an_answer_with_an_empty_books_list_is_a_valid_read_of_an_empty_shelf(tmp_path):
    work, _ = cut_small_photo(tmp_path)

    read = run_read(work, "b-spark", "pi", run=FakeRun(stdout='{"file": "shelf-1.jpg", "books": []}'))

    assert read["books"] == []
    assert read["complete"] is True
    assert (read_dir_of(work, "b-spark") / "read.json").exists()


@pytest.mark.parametrize("line", ["not json at all", '{"type": "item.started", "item": {"id": "item_1", "ty', "[1, 2]", "42"])
def test_a_line_of_the_codex_stream_that_is_not_a_json_object_fails_the_read(tmp_path, line):
    work, _ = cut_small_photo(tmp_path)
    stdout = codex_stream().replace("\n", "\n" + line + "\n", 1)
    run = FakeRun(stdout=stdout)

    with pytest.raises(ReadError, match="not a JSON object"):
        run_read(work, "a-sol", "codex-exec", run=run)

    read_dir = read_dir_of(work, "a-sol")
    assert not (read_dir / "read.json").exists()
    assert (read_dir / "raw.txt").read_text(encoding="utf-8") == ANSWER
    assert (read_dir / "events.jsonl").read_text(encoding="utf-8") == stdout
    assert (read_dir / "run.json").exists()


@pytest.mark.parametrize("kind", ["turn.failed", "error"])
def test_a_codex_stream_with_a_failure_event_fails_the_read_even_after_an_answer(tmp_path, kind):
    work, _ = cut_small_photo(tmp_path)
    run = FakeRun(stdout=codex_stream(extra=[{"type": kind, "message": "boom"}]))

    with pytest.raises(ReadError, match=f"'{kind}' event"):
        run_read(work, "a-sol", "codex-exec", run=run)

    read_dir = read_dir_of(work, "a-sol")
    assert not (read_dir / "read.json").exists()
    assert (read_dir / "raw.txt").read_text(encoding="utf-8") == ANSWER
    assert (read_dir / "events.jsonl").exists()
    assert (read_dir / "run.json").exists()


def test_an_item_without_a_type_counts_as_a_tool_call_named_unknown(tmp_path):
    work, _ = cut_small_photo(tmp_path)
    run = FakeRun(stdout=codex_stream(extra=[{"type": "item.started", "item": {"id": "item_1"}}]))

    with pytest.raises(ReadError, match=r"used tools \(unknown\)"):
        run_read(work, "a-sol", "codex-exec", run=run)

    info = json.loads((read_dir_of(work, "a-sol") / "run.json").read_text(encoding="utf-8"))
    assert info["tool_calls"] == ["unknown"]
    assert not (read_dir_of(work, "a-sol") / "read.json").exists()
