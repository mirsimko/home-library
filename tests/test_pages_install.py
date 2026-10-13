"""The phones can install the app: a manifest, icons made on demand, and a service worker that caches nothing."""
from io import BytesIO

from PIL import Image
from web_helpers import anonymous as anonymous
from web_helpers import client as client


def test_manifest_describes_an_installable_standalone_app(client):
    response = client.get("/manifest.webmanifest")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/manifest+json")
    manifest = response.json()
    assert manifest["name"] == "Home library" and manifest["short_name"] == "Library"
    assert manifest["start_url"] == "/capture" and manifest["display"] == "standalone"
    assert manifest["scope"] == "/"
    assert manifest["theme_color"].startswith("#") and manifest["background_color"].startswith("#")
    sizes = {icon["sizes"]: icon for icon in manifest["icons"]}
    assert set(sizes) >= {"192x192", "512x512"}
    for icon in sizes.values():
        assert icon["type"] == "image/png"
        assert client.get(icon["src"]).status_code == 200


def test_icons_are_valid_square_pngs_of_the_requested_size(client):
    for size in (180, 192, 512):
        response = client.get(f"/icons/icon-{size}.png")
        assert response.status_code == 200 and response.headers["content-type"] == "image/png"
        with Image.open(BytesIO(response.content)) as image:
            assert image.format == "PNG" and image.size == (size, size)
            assert len(image.convert("RGB").getcolors(maxcolors=100000)) > 2
    assert client.get("/icons/icon-64.png").status_code == 404
    assert client.get("/icons/icon-512.png").content == client.get("/icons/icon-512.png").content


def test_service_worker_installs_claims_clients_and_caches_nothing(client):
    response = client.get("/sw.js")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/javascript")
    assert response.headers["cache-control"] == "no-cache"
    worker = response.text
    assert "skipWaiting" in worker and "clients.claim" in worker and "fetch" in worker
    assert "caches" not in worker.replace("caches nothing", "")
    assert '"/sw.js"' in client.get("/static/app.js").text
    assert '<link rel="manifest" href="/manifest.webmanifest">' in client.get("/").text


def test_install_files_need_access_too(anonymous):
    for path in ("/manifest.webmanifest", "/sw.js", "/icons/icon-192.png"):
        assert anonymous.get(path).status_code == 401
