"""static/review.js: the review keys, with the key rules run under Node."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from web_helpers import client as client

SCRIPT = Path(__file__).resolve().parent.parent / "src/home_library/web/static/review.js"
node = pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed")


def run_node(body):
    program = f"const hl = require({json.dumps(str(SCRIPT))}); const out = (value) => console.log(JSON.stringify(value));\n{body}"
    result = subprocess.run(["node", "-e", program], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_script_is_served_and_the_detail_page_loads_it_with_its_key_legend(client):
    script = client.get("/static/review.js")
    assert script.status_code == 200 and "javascript" in script.headers["content-type"]
    assert "data-fill" in script.text and "requestSubmit" in script.text
    assert "https://" not in script.text


@node
def test_script_is_valid_modern_javascript():
    result = subprocess.run(["node", "--check", str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@node
def test_keys_act_only_when_the_person_is_not_typing():
    actions = run_node("""
      const idle = { typing: false, textarea: false, onControl: false };
      const typing = { typing: true, textarea: false, onControl: false };
      const area = { typing: true, textarea: true, onControl: false };
      const control = { typing: false, textarea: false, onControl: true };
      const press = (key, context, extra) => hl.keyAction(Object.assign({ key }, extra || {}), context);
      out({
        idle: ["j", "k", "e", "x", "Enter", "a"].map((key) => press(key, idle)),
        typing: ["j", "k", "e", "x", "Enter"].map((key) => press(key, typing)),
        area: ["j", "Enter"].map((key) => press(key, area)),
        control: ["j", "Enter"].map((key) => press(key, control)),
        escape: [press("Escape", typing), press("Escape", idle)],
        modified: [press("j", idle, { ctrlKey: true }), press("x", idle, { metaKey: true }), press("e", idle, { altKey: true })],
        submitAnywhere: [press("Enter", area, { ctrlKey: true }), press("Enter", typing, { metaKey: true })],
      });""")
    assert actions["idle"] == ["next", "prev", "edit", "dismiss", "approve", None]
    assert actions["typing"] == [None] * 5
    assert actions["area"] == [None, None]
    assert actions["control"] == ["next", None]
    assert actions["escape"] == ["blur", None]
    assert actions["modified"] == [None, None, None]
    assert actions["submitAnywhere"] == ["approve", "approve"]


@node
def test_row_focus_moves_one_step_and_stops_at_the_ends():
    moves = run_node("out([hl.moveFocus(-1, 5, 'next'), hl.moveFocus(0, 5, 'next'), hl.moveFocus(4, 5, 'next'), hl.moveFocus(0, 5, 'prev'), hl.moveFocus(3, 5, 'prev'), hl.moveFocus(-1, 5, 'prev'), hl.moveFocus(-1, 0, 'next')]);")
    assert moves == [0, 1, 4, 0, 2, 4, -1]
