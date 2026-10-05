"""Stage 2: one model session over the tiles of one photo (see docs/pipeline.md)."""
import json
import subprocess
import time
from datetime import datetime
from importlib import resources
from pathlib import Path

from home_library.parse import parse_read

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


def _answer(events):
    answer = ""
    for event in events:
        item = event.get("item") or {}
        if event.get("type") == "item.completed" and item.get("type") == "agent_message":
            answer = item.get("text", "")
    return answer


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


def run_read(photo_dir, read_id, backend, *, run=subprocess.run, clock=time.monotonic,
             now=lambda: datetime.now().astimezone(), timeout=600):
    """Run one read of the photo in photo_dir and return the stored read."""
    photo_dir = Path(photo_dir)
    manifest = json.loads((photo_dir / "tiles.json").read_text(encoding="utf-8"))
    tiles_dir = photo_dir / "tiles"
    files = [tile["file"] for tile in manifest["tiles"]]
    prompt = render_prompt(manifest)
    read_dir = photo_dir / "reads" / read_id
    read_dir.mkdir(parents=True, exist_ok=True)
    (read_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    result = run(_codex_command(tiles_dir, files), input=prompt, capture_output=True, text=True,
                 encoding="utf-8", cwd=tiles_dir, timeout=timeout)
    answer = _answer(_events(result.stdout))
    (read_dir / "events.jsonl").write_text(result.stdout, encoding="utf-8")
    (read_dir / "raw.txt").write_text(answer, encoding="utf-8")
    read = parse_read(answer)
    read["read_id"] = read_id
    (read_dir / "read.json").write_text(json.dumps(read, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return read
