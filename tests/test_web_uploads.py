"""Generated phone uploads retain their content and safe stored names."""
import hashlib
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image
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


def test_an_mpo_photo_from_an_android_camera_is_kept_as_a_jpeg(client, tmp_path):
    output = BytesIO()
    first, second = Image.new("RGB", (4080, 3072), "white"), Image.new("RGB", (400, 300), "gray")
    first.save(output, "MPO", save_all=True, append_images=[second])
    content = output.getvalue()
    with Image.open(BytesIO(content)) as check:
        assert check.format == "MPO"
    response = upload(client, content)
    assert response.status_code == 201
    assert response.json()["capture"]["media_type"] == "image/jpeg"
    assert (tmp_path / "captures" / f"{CAPTURE_ID}.jpg").read_bytes() == content


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



def test_retries_keep_the_stored_receipt_and_file_while_hash_conflicts_leave_it_untouched(client, tmp_path):
    content = photo(size=(20, 10))
    first = upload(client, content).json()
    stored = tmp_path / "captures" / f"{CAPTURE_ID}.jpg"
    before = stored.stat()
    repeated = upload(client, content, kind="cover", state="Stored")
    assert repeated.status_code == 200
    assert repeated.json() == {**first, "created": False}
    assert stored.stat().st_mtime_ns == before.st_mtime_ns and stored.stat().st_ino == before.st_ino
    conflict = upload(client, photo("PNG", size=(10, 10)))
    assert conflict.status_code == 409 and "different photo hash" in conflict.json()["error"]
    assert stored.read_bytes() == content
    assert not (tmp_path / "captures" / f"{CAPTURE_ID}.png").exists()


def test_oversize_uploads_stop_before_reading_the_rest_of_the_body(client, tmp_path):
    client.post("/api/locations", json={"name": "Shelf A", "kind": "shelf"})
    consumed = []

    def body():
        yield (b'--test\r\nContent-Disposition: form-data; name="file"; filename="big.jpg"\r\n\r\n')
        for index in range(42):
            consumed.append(index)
            yield b"x" * 1_000_000
        yield b"\r\n--test--\r\n"

    # TestClient buffers HTTPX generators; deliver separate ASGI chunks at the transport boundary.
    chunks = iter(body())

    async def streaming_app(scope, receive, send):
        async def streamed_receive():
            chunk = next(chunks, b"")
            return {"type": "http.request", "body": chunk, "more_body": bool(chunk)}
        await client.app(scope, streamed_receive, send)

    streamed = TestClient(streaming_app)
    response = streamed.post("/api/captures", headers={
        "Content-Type": "multipart/form-data; boundary=test", "Sec-Fetch-Site": "same-origin"})
    assert response.status_code == 413 and list(response.json()) == ["error"]
    assert len(consumed) <= 41
    assert not list((tmp_path / "captures" / ".incoming").glob("*.tmp"))


def test_the_upload_limit_allows_exactly_forty_megabytes(client, tmp_path):
    image = photo(size=(20, 10))
    content = image + b"\0" * (40_000_000 - len(image))
    response = upload(client, content)
    assert response.status_code == 201
    assert response.json()["capture"]["bytes"] == 40_000_000
    assert (tmp_path / "captures" / f"{CAPTURE_ID}.jpg").stat().st_size == 40_000_000


def test_a_symlink_cannot_redirect_capture_publication_outside_captures(client, tmp_path):
    outside = tmp_path / "keep.txt"
    outside.write_bytes(b"keep these bytes")
    (tmp_path / "captures" / f"{CAPTURE_ID}.jpg").symlink_to(outside)
    response = upload(client, photo(size=(20, 10)))
    assert response.status_code == 400
    assert outside.read_bytes() == b"keep these bytes"
    assert not list((tmp_path / "captures" / ".incoming").glob("*.tmp"))


def test_photo_bytes_are_fsynced_and_published_before_the_store_records_them(client, tmp_path, monkeypatch):
    import os
    from contextlib import closing

    from home_library import store

    content = photo(size=(20, 10))
    events = []
    fsync, replace = os.fsync, os.replace

    def flushed(fd):
        events.append("fsync")
        fsync(fd)

    def published(source, destination):
        events.append("replace")
        assert source.parent == tmp_path / "captures" / ".incoming"
        assert source.read_bytes() == content
        with closing(store.open(tmp_path)) as db:
            with pytest.raises(store.NotFound):
                store.capture(db, CAPTURE_ID)
        replace(source, destination)

    monkeypatch.setattr(os, "fsync", flushed)
    monkeypatch.setattr(os, "replace", published)
    assert upload(client, content).status_code == 201
    assert events == ["fsync", "replace"]


def test_simultaneous_retries_publish_one_file_and_one_job(client, tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    client.post("/api/locations", json={"name": "Shelf A", "kind": "shelf"})
    content = photo(size=(20, 10))

    def send():
        return client.post("/api/captures", data={"id": CAPTURE_ID, "kind": "shelf", "location_id": "1"},
                           files={"file": ("invented.jpg", content, "image/jpeg")})

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: send(), range(2)))
    assert sorted(response.status_code for response in responses) == [200, 201]
    assert len(client.get("/api/jobs").json()) == 1
    assert (tmp_path / "captures" / f"{CAPTURE_ID}.jpg").read_bytes() == content


def test_failed_publication_removes_temporary_bytes_and_does_not_queue_a_capture(client, tmp_path, monkeypatch):
    import os

    def fail_replace(source, destination):
        raise OSError("invented disk failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    response = upload(client, photo(size=(20, 10)))
    assert response.status_code == 503 and response.json() == {"error": "the photo could not be stored; retry the upload"}
    assert client.get("/api/captures").json() == [] and client.get("/api/jobs").json() == []
    assert not list((tmp_path / "captures" / ".incoming").glob("*.tmp"))


@pytest.mark.parametrize("body", [
    b"--test\r\nContent-Disposition: form-data; name=\"file\"; filename=\"incomplete.jpg\"\r\n\r\nunfinished",
    b"--test\r\nContent-Disposition: form-data; name=\"id\"\r\n\r\none\r\n"
    b"--test\r\nContent-Disposition: form-data; name=\"id\"\r\n\r\ntwo\r\n--test--\r\n",
])
def test_incomplete_and_duplicate_multipart_fields_leave_no_temporary_files(client, tmp_path, body):
    response = client.post("/api/captures", content=body, headers={"Content-Type": "multipart/form-data; boundary=test"})
    assert response.status_code == 400 and list(response.json()) == ["error"]
    assert client.get("/api/captures").json() == []
    assert not list((tmp_path / "captures" / ".incoming").glob("*.tmp"))
