import json
import subprocess
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from PIL import Image

from home_library.reader import ReadError, render_prompt, run_read
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
    stdout = "not json at all\n" + codex_stream(extra=[reasoning, early])
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


def test_usage_is_null_when_the_stream_has_no_turn_completed(tmp_path):
    work, _ = cut_small_photo(tmp_path)
    message = {"type": "item.completed", "item": {"id": "item_0", "type": "agent_message", "text": ANSWER}}
    run = FakeRun(stdout=json.dumps(message) + "\n")

    run_read(work, "a-sol", "codex-exec", run=run)

    info = json.loads((work / "reads" / "a-sol" / "run.json").read_text(encoding="utf-8"))
    assert info["usage"] is None


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
    assert kwargs.get("input") is None
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
