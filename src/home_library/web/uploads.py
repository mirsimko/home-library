"""Stream multipart photos into private temporary files and publish verified content."""
import fcntl
import hashlib
import os
from contextlib import asynccontextmanager, closing
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError
from python_multipart import MultipartParser
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import parse_options_header

from home_library import store
from home_library.workspace import refuse_inside_checkout

MAX_BYTES = 40_000_000

# Pillow reports a JPEG that carries a second image (Android Ultra HDR) as MPO.
FORMATS = {"JPEG": ("jpg", "image/jpeg"), "MPO": ("jpg", "image/jpeg"), "PNG": ("png", "image/png"), "WEBP": ("webp", "image/webp")}


class MultipartPhoto:
    """Keep file bytes on disk while retaining only small form fields in memory."""

    def __init__(self, target):
        self.target = target
        self.fields = {}
        self.filename = None
        self.hash = hashlib.sha256()
        self.bytes = 0
        self.complete = False

    def part_begin(self):
        self.headers = {}
        self.header_name = bytearray()
        self.header_value = bytearray()
        self.value = bytearray()

    def header_field(self, data, start, end):
        self.header_name.extend(data[start:end])
        self.check_header_size()

    def header_value_data(self, data, start, end):
        self.header_value.extend(data[start:end])
        self.check_header_size()

    def check_header_size(self):
        if len(self.header_name) + len(self.header_value) > 16384:
            raise HTTPException(400, "multipart header is too large")

    def header_end(self):
        self.headers[bytes(self.header_name).lower()] = bytes(self.header_value)
        self.header_name.clear()
        self.header_value.clear()

    def headers_finished(self):
        _, options = parse_options_header(self.headers.get(b"content-disposition", b""))
        self.name = options.get(b"name", b"").decode("utf-8")
        self.is_file = b"filename" in options
        if self.name in self.fields or len(self.fields) >= 16:
            raise HTTPException(400, "duplicate or too many multipart fields")
        if self.is_file:
            if self.name != "file" or self.filename is not None:
                raise HTTPException(400, "choose exactly one file")
            self.filename = options[b"filename"].decode("utf-8")

    def part_data(self, data, start, end):
        chunk = data[start:end]
        if self.is_file:
            if self.bytes + len(chunk) > MAX_BYTES:
                raise HTTPException(413, "the photo must be at most 40 MB")
            self.bytes += len(chunk)
            self.hash.update(chunk)
            self.target.write(chunk)
        else:
            if len(self.value) + len(chunk) > 65536:
                raise HTTPException(400, "multipart field is too large")
            self.value.extend(chunk)

    def part_end(self):
        if not self.is_file:
            self.fields[self.name] = self.value.decode("utf-8")

    def end(self):
        self.complete = True


@asynccontextmanager
async def incoming(request):
    """Remove temporary bytes on success, rejection, or a disconnected upload."""
    content_type, options = parse_options_header(request.headers.get("content-type", ""))
    boundary = options.get(b"boundary")
    if content_type != b"multipart/form-data" or not boundary or len(boundary) > 200:
        raise HTTPException(400, "a multipart photo upload is required")
    directory = refuse_inside_checkout(request.app.state.data_root / "captures" / ".incoming")
    directory.mkdir(exist_ok=True)
    with NamedTemporaryFile(dir=directory, suffix=".tmp", delete=False) as target:
        path = Path(target.name)
        upload = MultipartPhoto(target)
        callbacks = {"on_" + name: getattr(upload, method) for name, method in (
            ("part_begin", "part_begin"), ("header_field", "header_field"),
            ("header_value", "header_value_data"), ("header_end", "header_end"),
            ("headers_finished", "headers_finished"), ("part_data", "part_data"),
            ("part_end", "part_end"), ("end", "end"))}
        parser = MultipartParser(boundary, callbacks)
        try:
            async for chunk in request.stream():
                # A server may deliver a large chunk; keep parser callback buffers bounded too.
                for offset in range(0, len(chunk), 65536):
                    parser.write(chunk[offset:offset + 65536])
            parser.finalize()
            if not upload.complete or upload.filename is None:
                raise HTTPException(400, "a complete multipart file is required")
            target.flush()
            os.fsync(target.fileno())
            yield path, upload
        except (MultipartParseError, UnicodeError) as error:
            raise HTTPException(400, "the multipart upload could not be read") from error
        finally:
            path.unlink(missing_ok=True)


def image_info(path):
    """Read original pixel dimensions and orientation, without rotating or resizing."""
    try:
        with Image.open(path) as image:
            if image.format not in FORMATS:
                raise HTTPException(415, "choose a JPEG, PNG or WebP photo")
            image.verify()
        with Image.open(path) as image:
            return {"width": image.width, "height": image.height, "format": "JPEG" if image.format == "MPO" else image.format,
                    "orientation": image.getexif().get(274)}
    except (OSError, ValueError, SyntaxError, UnidentifiedImageError, Image.DecompressionBombError) as error:
        raise HTTPException(415, "choose a readable JPEG, PNG or WebP photo") from error


def publish(root, path, upload, user):
    """Serialize publication so a retried capture never replaces the stored photo."""
    info = image_info(path)
    extension, media_type = FORMATS[info["format"]]
    fields = upload.fields
    location_id = fields.get("location_id")
    try:
        location_id = int(location_id)
    except (TypeError, ValueError):
        pass  # The store gives the same validation message as its other callers.
    metadata = dict(id=fields.get("id"), kind=fields.get("kind"), location_id=location_id,
                    default_state=fields.get("state", "Active"), group_id=fields.get("group_id"),
                    uploaded_by=user, original_name=upload.filename, media_type=media_type,
                    sha256=upload.hash.hexdigest(), bytes=upload.bytes)
    lock_path = refuse_inside_checkout(root / "captures" / ".incoming" / ".lock")
    with lock_path.open("a") as lock, closing(store.open(root)) as db:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            existing = store.validate_capture(db, **metadata)
        except store.NotFound as error:
            # A nonexistent upload location is malformed metadata, rather than a missing URL.
            raise store.Invalid(str(error)) from error
        if existing is not None:
            return {**existing, "image": info}
        destination = root / "captures" / f"{metadata['id']}.{extension}"
        refuse_inside_checkout(destination)
        if destination.is_symlink() or not destination.resolve().is_relative_to((root / "captures").resolve()):
            raise store.Invalid("capture files must stay inside captures")
        os.replace(path, destination)
        try:
            receipt = store.add_capture(db, **metadata)
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
    return {**receipt, "image": info}
