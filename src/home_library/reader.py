"""Stage 2: one model session over the tiles of one photo (see docs/pipeline.md)."""
import json
import subprocess
import time
from datetime import datetime
from importlib import resources
from pathlib import Path
from types import SimpleNamespace

from home_library.parse import parse_read
from home_library.workspace import refuse_inside_checkout


class ReadError(Exception):
    """A read failed; raw.txt and run.json, where there were any, are left for inspection."""


BACKENDS = {"codex-exec": "gpt-6.1-sol", "pi": "opencode-go/muse-spark-1.3-contributor"}


def _template():
    return resources.files("home_library").joinpath("prompts", "shelf_read.txt").read_text(encoding="utf-8")


def render_prompt(manifest):
    """Fill the prompt template from a tiles.json manifest."""
    layout = manifest["layout"]
    rows, columns = len(layout["rows"]), len(layout["columns"])
    values = {
        "COUNT": str(len(manifest["tiles"])),
        "TILES": str(rows * columns),
        "ROWS": str(rows),
        "COLUMNS": str(columns),
        "FILES": " ".join(tile["file"] for tile in manifest["tiles"]),
        "PHOTO": manifest["photo"],
    }
    prompt = _template()
    for name, value in values.items():
        prompt = prompt.replace(f"<<{name}>>", value)
    return prompt


def _codex_command(tiles_dir, files):
    return ["codex", "exec", "--ignore-user-config", "-m", BACKENDS["codex-exec"],
            "-c", 'model_reasoning_effort="low"', "-s", "read-only", "--skip-git-repo-check", "--ephemeral",
            "-C", str(tiles_dir), "-i", ",".join(files), "--json", "-"]


def _pi_command(files, prompt):
    return ["pi", "-p", "--model", BACKENDS["pi"], "--thinking", "medium", "--no-context-files", "--no-skills",
            "--no-prompt-templates", "--no-extensions", "--no-tools", "--no-session",
            *[f"@{name}" for name in files], prompt]


def _answer(events):
    answer = ""
    for event in events:
        item = event.get("item") or {}
        if event.get("type") == "item.completed" and item.get("type") == "agent_message":
            answer = item.get("text", "")
    return answer


def _tool_calls(events):
    """The item type of every item that is neither reasoning nor an answer, once per item id."""
    seen = {}
    for event in events:
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") not in ("agent_message", "reasoning"):
            seen.setdefault(item.get("id"), item.get("type"))
    return list(seen.values())


def _usage(events):
    for event in events:
        if event.get("type") == "turn.completed":
            return event.get("usage")
    return None


def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _events(stdout):
    events = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _check_tiles(tiles_dir, files):
    present = {entry.name for entry in tiles_dir.iterdir()}
    extra = sorted(present - set(files))
    missing = sorted(name for name in set(files) if not (tiles_dir / name).is_file())
    if extra:
        raise ReadError(f"{tiles_dir} holds files the manifest does not list: {', '.join(extra)}")
    if missing:
        raise ReadError(f"{tiles_dir} lacks files the manifest lists: {', '.join(missing)}")


def _execute(command, stdin, cwd, run, timeout):
    """Run the command; return (result, failure) where failure is None unless it timed out or is missing."""
    try:
        return run(command, input=stdin, capture_output=True, text=True,
                   encoding="utf-8", cwd=cwd, timeout=timeout), None
    except subprocess.TimeoutExpired as expired:
        partial = expired.stdout or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", errors="replace")
        return (SimpleNamespace(returncode=None, stdout=partial),
                f"{command[0]} timed out after {timeout} seconds")
    except FileNotFoundError:
        return SimpleNamespace(returncode=None, stdout=""), f"{command[0]} is not installed"


def run_read(photo_dir, read_id, backend, *, run=subprocess.run, clock=time.monotonic,
             now=lambda: datetime.now().astimezone(), timeout=600):
    """Run one read of the photo in photo_dir and return the stored read.

    Raises ReadError for a work directory inside a git checkout, an unknown backend, a tiles directory that
    does not match the manifest, and any failed run. Any attempt, failed or refused, first removes the read.json
    and events.jsonl of an earlier run of the same read. A failed run leaves raw.txt and run.json, never read.json.
    """
    try:
        photo_dir = refuse_inside_checkout(photo_dir)
    except ValueError as error:
        raise ReadError(str(error)) from error
    read_dir = photo_dir / "reads" / read_id
    (read_dir / "read.json").unlink(missing_ok=True)
    (read_dir / "events.jsonl").unlink(missing_ok=True)
    if backend not in BACKENDS:
        raise ReadError(f"unknown backend {backend!r}; choose one of {', '.join(BACKENDS)}")
    manifest = json.loads((photo_dir / "tiles.json").read_text(encoding="utf-8"))
    tiles_dir = photo_dir / "tiles"
    files = [tile["file"] for tile in manifest["tiles"]]
    _check_tiles(tiles_dir, files)
    prompt = render_prompt(manifest)
    read_dir.mkdir(parents=True, exist_ok=True)
    (read_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    if backend == "codex-exec":
        command = logged = _codex_command(tiles_dir, files)
        stdin = prompt
    else:
        command = _pi_command(files, prompt)
        logged = [*command[:-1], "<prompt>"]
        stdin = None
    started = now().isoformat()
    began = clock()
    result, failure = _execute(command, stdin, tiles_dir, run, timeout)
    seconds = clock() - began
    if backend == "codex-exec":
        events = _events(result.stdout)
        answer, tool_calls, usage = _answer(events), _tool_calls(events), _usage(events)
        (read_dir / "events.jsonl").write_text(result.stdout, encoding="utf-8")
    else:
        answer, tool_calls, usage = result.stdout, [], None
    (read_dir / "raw.txt").write_text(answer, encoding="utf-8")
    _write_json(read_dir / "run.json", {
        "read_id": read_id, "backend": backend, "model": BACKENDS[backend], "command": logged,
        "started": started, "seconds": seconds, "returncode": result.returncode, "tool_calls": tool_calls,
        "usage": usage})
    if failure is None and result.returncode != 0:
        failure = f"{command[0]} exited with return code {result.returncode}"
    if failure is None and not answer.strip():
        failure = f"empty answer from {command[0]}"
    if failure is None and tool_calls:
        failure = f"the read used tools ({', '.join(tool_calls)}) and is not blind"
    if failure is not None:
        raise ReadError(failure)
    read = parse_read(answer)
    read["read_id"] = read_id
    read["file"] = read["file"] or manifest["photo"]
    _write_json(read_dir / "read.json", read)
    return read
