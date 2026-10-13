"""Real OS signals stop a worker without completing or failing an interrupted lease."""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from store_helpers import capture
from test_worker import queued

from home_library import store


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGINT])
@pytest.mark.parametrize("active", [True, False])
def test_signals_stop_active_and_idle_workers_and_restore_handlers(tmp_path, sig, active):
    root = tmp_path / "private"
    if active:
        queued(root)
    pid_file = tmp_path / "child.pid"
    child_script = tmp_path / "fake_hl.py"
    child_script.write_text("import time\ntime.sleep(60)\n")
    driver = tmp_path / "driver.py"
    driver.write_text(
        "import signal, subprocess, sys\n"
        "from pathlib import Path\n"
        "from home_library.cli import main\n"
        "signals = (signal.SIGTERM, signal.SIGINT)\n"
        "original = [signal.getsignal(sig) for sig in signals]\n"
        "def popen(command, **kwargs):\n"
        f"    child = subprocess.Popen([sys.executable, {str(child_script)!r}], **kwargs)\n"
        f"    Path({str(pid_file)!r}).write_text(str(child.pid))\n"
        "    return child\n"
        f"code = main(['worker', '--data-root', {str(root)!r}], popen=popen)\n"
        "assert original == [signal.getsignal(sig) for sig in signals]\n"
        "sys.exit(code)\n")
    process = subprocess.Popen([sys.executable, str(driver)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        ready = pid_file if active else root / "catalog.db"
        deadline = time.monotonic() + 5
        while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.exists()
        process.send_signal(sig)
        stdout, stderr = process.communicate(timeout=5)
        assert process.returncode == 0, stderr.decode()
        assert stdout == b""
        if active:
            db = store.open(root)
            job = capture(db)["job"]
            assert job["status"] == "running" and job["owner"] and job["error"] is None
            assert store.observations(db) == []
            db.close()
            child = Path(f"/proc/{pid_file.read_text()}/stat")
            assert not child.exists() or child.read_text().split()[2] == "Z"
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        if pid_file.exists():
            try:
                os.killpg(int(pid_file.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass
