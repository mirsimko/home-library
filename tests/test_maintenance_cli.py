"""Tokens and backups stay private, using temporary roots only."""
import base64
import hashlib
import stat
from pathlib import Path

import pytest

from home_library.cli import main


@pytest.mark.parametrize("position", ["before", "after", "environment", "home"])
def test_token_rotation_prints_random_secret_and_saves_only_its_private_hash(tmp_path, capsys, monkeypatch, position):
    root = tmp_path / "private" if position != "home" else tmp_path / "home-library"
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("HL_DATA", raising=False)
    args = ["token"]
    if position == "environment":
        monkeypatch.setenv("HL_DATA", str(root))
    elif position in ("before", "after"):
        index = 0 if position == "before" else 1
        args[index:index] = ["--data-root", str(root)]
    root.mkdir()
    target = root / "agent-token"
    target.write_text("old hash")
    target.chmod(0o644)
    secrets = []
    for _ in range(2):
        assert main(args) == 0
        output = capsys.readouterr()
        token = output.out.strip()
        assert len(output.out.splitlines()) == 1 and output.err == ""
        assert len(base64.urlsafe_b64decode(token + "=")) == 32
        assert target.read_text().strip() == hashlib.sha256(token.encode()).hexdigest()
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
        secrets.append(token)
    assert secrets[0] != secrets[1]


def test_token_refuses_checkout_and_symlinked_checkout_target(tmp_path, capsys):
    checkout = tmp_path / "repo"
    checkout.mkdir()
    (checkout / ".git").mkdir()
    root = tmp_path / "private"
    root.mkdir()
    (root / "agent-token").symlink_to(checkout / "secret")
    for target in (checkout / "data", root):
        assert main(["token", "--data-root", str(target)]) == 1
        output = capsys.readouterr()
        assert output.out == "" and "git checkout" in output.err
    assert not (checkout / "secret").exists()
