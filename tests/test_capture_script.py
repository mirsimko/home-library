"""static/capture.js: served, valid, and its upload rules checked by running the pure logic under Node."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from web_helpers import client as client

SCRIPT = Path(__file__).resolve().parent.parent / "src/home_library/web/static/capture.js"
node = pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed")


def run_node(body):
    """Evaluate JavaScript with the script's exports in scope; return what it prints as JSON."""
    program = f"const hl = require({json.dumps(str(SCRIPT))}); const out = (value) => console.log(JSON.stringify(value));\n{body}"
    result = subprocess.run(["node", "-e", program], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_script_is_served_and_names_the_documented_endpoints_and_labels(client):
    response = client.get("/static/capture.js")
    assert response.status_code == 200 and "javascript" in response.headers["content-type"]
    script = response.text
    for label in ("on this phone", "received", "reading", "needs attention", "ready for review"):
        assert f'"{label}"' in script
    for needle in ("XMLHttpRequest", "crypto.randomUUID", "/api/captures", "localStorage", "capture.js"):
        assert needle in script
    assert "https://" not in script and "http://" not in script


@node
def test_script_is_valid_modern_javascript():
    result = subprocess.run(["node", "--check", str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@node
def test_status_labels_follow_the_upload_and_the_job():
    labels = run_node("""
      const item = (state, job, open) => ({ state, job: job ? { status: job } : null, open_observations: open || 0 });
      out([
        hl.statusOf(item("waiting")), hl.statusOf(item("sending")), hl.statusOf(item("backoff")),
        hl.statusOf(item("failed")), hl.statusOf(item("rejected")),
        hl.statusOf(item("uploaded")), hl.statusOf(item("uploaded", "queued")),
        hl.statusOf(item("uploaded", "running")), hl.statusOf(item("uploaded", "failed")),
        hl.statusOf(item("uploaded", "done", 3)), hl.statusOf(item("uploaded", "done", 0)),
      ]);""")
    assert labels == ["on this phone"] * 3 + ["needs attention"] * 2 + ["received"] * 2 + [
        "reading", "needs attention", "ready for review", "needs attention"]


@node
def test_photos_under_three_thousand_pixels_are_flagged_by_their_long_side():
    flags = run_node("out([hl.isSmall(4080, 3072), hl.isSmall(3072, 4080), hl.isSmall(3000, 2000), hl.isSmall(2999, 2999), hl.isSmall(1600, 1200)]);")
    assert flags == [False, False, False, True, True]


@node
def test_one_book_mode_walks_cover_then_optional_barcode_with_a_shared_group():
    steps = run_node("""
      let n = 0; const newId = () => "g" + (++n);
      let flow = hl.startFlow("book");
      const cover = hl.assign(flow, newId); flow = cover.flow;
      const asked = hl.askBarcode(flow);
      const barcode = hl.assign(asked, newId);
      const second = hl.assign(barcode.flow, newId);
      const skipped = hl.assign(hl.nextBook(second.flow), newId);
      const shelf = hl.assign(hl.startFlow("shelf"), newId);
      out({ cover: [cover.kind, cover.group_id, cover.flow.step], barcode: [barcode.kind, barcode.group_id, barcode.flow.step],
            second: [second.kind, second.group_id], skipped: [skipped.kind, skipped.group_id],
            shelf: [shelf.kind, shelf.group_id], prompts: [hl.prompt(hl.startFlow("shelf")), hl.prompt(hl.startFlow("book")), hl.prompt(cover.flow), hl.prompt(asked)] });""")
    assert steps["cover"] == ["cover", "g1", "after-cover"]
    assert steps["barcode"] == ["barcode", "g1", "cover"]
    assert steps["second"] == ["cover", "g2"] and steps["skipped"] == ["cover", "g3"]
    assert steps["shelf"] == ["shelf", None]
    assert len(set(steps["prompts"])) == 4 and all(steps["prompts"])


@node
def test_a_failed_upload_is_retried_five_times_with_doubling_waits_then_needs_attention():
    result = run_node("""
      const waits = []; const sent = []; const seen = [];
      const uploader = hl.createUploader({
        send: (item, done) => { sent.push(item.id); done({ ok: false, status: 0, message: "network" }); },
        schedule: (run, seconds) => waits.push([seconds, run]),
        changed: (item) => seen.push(item.state),
      });
      const item = { id: "a" };
      uploader.add(item);
      while (waits.length) { const [, run] = waits.shift(); run(); }
      out({ delays: hl.RETRY_DELAYS, sent: sent.length, state: item.state, failures: item.failures });""")
    assert result == {"delays": [2, 4, 8, 16, 32], "sent": 6, "state": "failed", "failures": 6}


@node
def test_retry_waits_are_the_documented_ones_and_a_rejection_is_not_retried():
    result = run_node("""
      const waits = []; let calls = 0;
      const uploader = hl.createUploader({
        send: (item, done) => { calls++; done(item.id === "bad" ? { ok: false, status: 415, message: "choose a JPEG" } : { ok: false, status: 503, message: "retry" }); },
        schedule: (run, seconds) => { waits.push(seconds); if (waits.length < 5) run(); },
        changed: () => {},
      });
      const flaky = { id: "flaky" }; const bad = { id: "bad" };
      uploader.add(flaky); uploader.add(bad);
      out({ waits, badState: bad.state, badMessage: bad.message, retryable: [0, 408, 429, 500, 503].map(hl.isRetryable), final: [400, 404, 413, 415].map(hl.isRetryable) });""")
    assert result["waits"][:4] == [2, 4, 8, 16]
    assert result["badState"] == "rejected" and result["badMessage"] == "choose a JPEG"
    assert result["retryable"] == [True] * 5 and result["final"] == [False] * 4


@node
def test_uploads_go_one_at_a_time_in_the_order_the_photos_were_chosen():
    result = run_node("""
      const pending = []; const order = [];
      const uploader = hl.createUploader({
        send: (item, done) => { order.push("start " + item.id); pending.push(() => { order.push("end " + item.id); done({ ok: true, receipt: { created: true, image: { width: 4000, height: 3000 } } }); }); },
        schedule: () => {}, changed: () => {},
      });
      const a = { id: "a" }; const b = { id: "b" };
      uploader.add(a); uploader.add(b);
      order.push("queued both");
      pending.shift()(); pending.shift()();
      out({ order, states: [a.state, b.state], width: a.receipt.image.width });""")
    assert result["order"] == ["start a", "queued both", "end a", "start b", "end b"]
    assert result["states"] == ["uploaded", "uploaded"] and result["width"] == 4000


@node
def test_a_photo_not_yet_received_warns_before_the_page_is_left():
    states = run_node("""
      const states = ["waiting", "sending", "backoff", "failed", "rejected", "uploaded"];
      out(states.map((state) => hl.isUnreceived({ state })));""")
    assert states == [True, True, True, True, False, False]
    assert "beforeunload" in SCRIPT.read_text() and "isUnreceived" in SCRIPT.read_text()


@node
def test_a_received_photo_lets_go_of_its_preview_and_its_file():
    result = run_node("""
      const revoked = [];
      const item = { state: "uploaded", thumbnail: "blob:invented", file: { name: "x.jpg" } };
      const waiting = { state: "backoff", thumbnail: "blob:other", file: { name: "y.jpg" } };
      hl.releasePreview(item, (url) => revoked.push(url));
      hl.releasePreview(waiting, (url) => revoked.push(url));
      hl.releasePreview(item, (url) => revoked.push(url));
      out({ revoked, item, waiting });""")
    assert result["revoked"] == ["blob:invented"]
    assert result["item"] == {"state": "uploaded", "thumbnail": None, "file": None}
    assert result["waiting"]["thumbnail"] == "blob:other" and result["waiting"]["file"] == {"name": "y.jpg"}
    assert "revokeObjectURL" in SCRIPT.read_text()


@node
def test_a_released_photo_has_no_preview_left_to_show():
    result = run_node("""
      const item = { state: "uploaded", thumbnail: "blob:invented", file: {} };
      const before = hl.hasPreview(item);
      hl.releasePreview(item, () => {});
      out({ before, after: hl.hasPreview(item), none: hl.hasPreview({ state: "waiting" }) });""")
    assert result == {"before": True, "after": False, "none": False}


@node
def test_only_a_shelf_photo_is_warned_about_for_being_small():
    flags = run_node("""out([hl.warnsSmall("shelf", 1600, 1200), hl.warnsSmall("shelf", 4080, 3072),
                           hl.warnsSmall("cover", 1600, 1200), hl.warnsSmall("barcode", 800, 600)]);""")
    assert flags == [True, False, False, False]
