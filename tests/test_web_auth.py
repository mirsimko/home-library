"""Access checks apply before any private handler runs."""
import hashlib

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from home_library.web import create_app


def client_for(tmp_path, **options):
    app = create_app(tmp_path, ["parent@example.test"], **options)

    @app.api_route("/identity", methods=["GET", "HEAD", "POST", "PATCH", "DELETE", "OPTIONS"])
    async def identity(request: Request):
        return {"user": request.state.user}

    return TestClient(app)


def test_only_get_health_is_public_and_allowed_logins_reach_handlers(tmp_path):
    client = client_for(tmp_path)
    assert client.get("/health").json() == {"ok": True, "worker_seen": None, "queued": 0, "failed": 0}
    for path in ("/identity", "/api/books", "/export.json", "/missing"):
        assert client.get(path).status_code == 401
    assert client.head("/health").status_code == 401
    assert client.get("/identity", headers={"Tailscale-User-Login": "stranger"}).status_code == 401
    assert client.get("/identity", headers={"Tailscale-User-Login": "parent@example.test"}).json() == {
        "user": "parent@example.test"}
    assert client_for(tmp_path, dev_user="local").get("/identity").json() == {"user": "local"}


def test_bearer_hash_is_checked_on_every_request_and_revocation_takes_effect(tmp_path):
    client = client_for(tmp_path)
    headers = {"Authorization": "Bearer invented-secret"}
    assert client.get("/identity", headers=headers).status_code == 401
    token_file = tmp_path / "agent-token"
    token_file.write_text(hashlib.sha256(b"invented-secret").hexdigest() + "\n")
    assert client.post("/identity", headers=headers).json() == {"user": "agent"}
    assert client.get("/identity", headers={"Authorization": "Bearer wrong"}).status_code == 401
    token_file.write_text(hashlib.sha256(b"replacement").hexdigest())
    assert client.get("/identity", headers=headers).status_code == 401
    token_file.write_text("not a hash")
    assert client.get("/identity", headers=headers).status_code == 401


@pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE", "OPTIONS"])
@pytest.mark.parametrize("proof, status", [
    ({}, 403), ({"Origin": "https://elsewhere.test"}, 403), ({"Origin": "null"}, 403),
    ({"Sec-Fetch-Site": "same-site"}, 403), ({"Origin": "https://testserver"}, 200),
    ({"Sec-Fetch-Site": "same-origin"}, 200), ({"Origin": "https://testserver:9999"}, 403),
])
def test_browser_writes_require_same_origin_including_in_development(tmp_path, method, proof, status):
    client = client_for(tmp_path, dev_user="local")
    assert client.request(method, "/identity", headers=proof).status_code == status
    assert client.head("/identity").status_code == 200
