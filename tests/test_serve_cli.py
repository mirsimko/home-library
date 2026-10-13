"""The serve command binds locally unless a person explicitly chooses otherwise."""
import pytest
import uvicorn
from fastapi.testclient import TestClient

from home_library.cli import main


@pytest.fixture
def calls(monkeypatch):
    for name in ("HL_USERS", "HL_DEV_USER", "HL_DATA", "UVICORN_HOST"):
        monkeypatch.delenv(name, raising=False)
    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **options: calls.append((app, options)))
    return calls


def test_serve_uses_private_data_environment_logins_and_only_local_proxy_headers(tmp_path, monkeypatch, calls):
    monkeypatch.setenv("HL_USERS", " parent@example.test , second@example.test , ")
    monkeypatch.setenv("HL_DATA", str(tmp_path))
    assert main(["serve"]) == 0
    app, options = calls[0]
    assert app.state.data_root == tmp_path
    assert options == {"host": "127.0.0.1", "port": 8765, "proxy_headers": True,
                       "forwarded_allow_ips": "127.0.0.1", "access_log": False}
    client = TestClient(app)
    assert client.get("/api/books", headers={"Tailscale-User-Login": "second@example.test"}).status_code == 200
    assert client.get("/api/books").status_code == 401


def test_serve_accepts_explicit_host_port_and_data_root(tmp_path, calls):
    assert main(["serve", "--data-root", str(tmp_path), "--host", "0.0.0.0", "--port", "9000"]) == 0
    assert calls[0][1]["host"] == "0.0.0.0" and calls[0][1]["port"] == 9000


def test_development_identity_is_allowed_only_on_literal_ipv4_loopback(tmp_path, monkeypatch, calls):
    monkeypatch.setenv("HL_DEV_USER", "developer")
    assert main(["serve", "--data-root", str(tmp_path)]) == 0
    assert TestClient(calls[0][0]).get("/api/books").status_code == 200
    for host in ("0.0.0.0", "localhost", "::1"):
        with pytest.raises(SystemExit) as error:
            main(["serve", "--data-root", str(tmp_path), "--host", host])
        assert error.value.code == 2
    assert len(calls) == 1


def test_a_nonlocal_environment_host_requires_an_explicit_argument(tmp_path, monkeypatch, calls, capsys):
    monkeypatch.setenv("UVICORN_HOST", "0.0.0.0")
    with pytest.raises(SystemExit) as error:
        main(["serve", "--data-root", str(tmp_path)])
    assert error.value.code == 2 and "explicit --host" in capsys.readouterr().err
    assert calls == []
    assert main(["serve", "--data-root", str(tmp_path), "--host=127.0.0.1"]) == 0


def test_serve_refuses_a_data_root_inside_a_checkout_before_starting(tmp_path, calls, capsys):
    (tmp_path / ".git").mkdir()
    with pytest.raises(SystemExit):
        main(["serve", "--data-root", str(tmp_path / "private")])
    assert "git checkout" in capsys.readouterr().err and calls == []


def test_serve_refuses_to_start_when_both_a_development_user_and_tailscale_logins_are_set(tmp_path, monkeypatch, calls, capsys):
    monkeypatch.setenv("HL_DEV_USER", "developer")
    monkeypatch.setenv("HL_USERS", "parent@example.test")
    with pytest.raises(SystemExit) as error:
        main(["serve", "--data-root", str(tmp_path)])
    message = capsys.readouterr().err
    assert error.value.code == 2 and "HL_DEV_USER" in message and "HL_USERS" in message
    assert calls == []
