"""Generated phone uploads retain their content and safe stored names."""
import hashlib

import pytest
from store_helpers import CAPTURE_ID, SECOND_ID
from web_helpers import client as client
from web_helpers import photo


def upload(client, content, **fields):
    location = client.post("/api/locations", json={"name": "Shelf A", "kind": "shelf"})
    assert location.status_code in (201, 400)
    return client.post("/api/captures", data={"id": CAPTURE_ID, "kind": "shelf", "location_id": "1", **fields},
                       files={"file": ("../../invented.exe", content, "application/octet-stream")})


@pytest.mark.parametrize("format, extension, media", [
    ("JPEG", "jpg", "image/jpeg"), ("PNG", "png", "image/png"), ("WEBP", "webp", "image/webp"),
])
def test_uploads_are_sniffed_and_keep_the_full_photo_and_orientation(client, tmp_path, format, extension, media):
    content = photo(format, orientation=6)
    response = upload(client, content, state="Stored", group_id=SECOND_ID)
    assert response.status_code == 201
    receipt = response.json()
    assert receipt["image"] == {"width": 4080, "height": 3072, "format": format, "orientation": 6}
    assert receipt["created"] is True and receipt["job"]["status"] == "queued"
    assert receipt["capture"]["uploaded_by"] == "parent"
    assert receipt["capture"]["original_name"] == "../../invented.exe"
    assert receipt["capture"]["media_type"] == media
    assert receipt["capture"]["sha256"] == hashlib.sha256(content).hexdigest()
    assert receipt["capture"]["bytes"] == len(content)
    assert receipt["capture"]["default_state"] == "Stored" and receipt["capture"]["group_id"] == SECOND_ID
    stored = tmp_path / "captures" / f"{CAPTURE_ID}.{extension}"
    assert stored.read_bytes() == content
    assert not list((tmp_path / "captures" / ".incoming").glob("*.tmp"))


@pytest.mark.parametrize("content", [b"not an image", photo("GIF", size=(20, 10)), photo("PNG", size=(20, 10))[:30]])
def test_unsupported_or_broken_photos_are_not_recorded(client, tmp_path, content):
    response = upload(client, content)
    assert response.status_code == 415 and list(response.json()) == ["error"]
    assert not list((tmp_path / "captures").glob(f"{CAPTURE_ID}.*"))


@pytest.mark.parametrize("fields, message", [
    ({"id": "../escape"}, "capture id must be a canonical lowercase UUID"),
    ({"kind": "portrait"}, "capture kind must be one of shelf, cover, barcode"),
    ({"location_id": "wrong"}, "locations id must be an integer"),
    ({"location_id": "999"}, "locations: 999 was not found"),
])
def test_upload_metadata_errors_use_store_messages_before_publishing(client, tmp_path, fields, message):
    response = upload(client, photo(size=(20, 10)), **fields)
    assert response.status_code == 400 and response.json() == {"error": message}
    assert not [path for path in (tmp_path / "captures").iterdir() if path.is_file()]

