"""Serve only stored photos and tile names recorded by the pipeline."""
import json
from pathlib import Path

from fastapi import HTTPException
from starlette.responses import FileResponse

from home_library.web.uploads import FORMATS

EXTENSIONS = {media: extension for extension, media in FORMATS.values()}
MEDIA_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def photo_path(root, capture):
    """Build the photo path from validated stored metadata, never a supplied filename."""
    return root / "captures" / f"{capture['id']}.{EXTENSIONS[capture['media_type']]}"


def checked_file(path, directory):
    """Reject missing files and symlinks that lead outside the expected directory."""
    if not path.is_file() or not path.resolve().is_relative_to(directory):
        raise HTTPException(404, "the image was not found")
    return path


def read_json(path, default):
    """Treat an absent or unfinished pipeline artefact as not available yet."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def photo_response(root, capture):
    path = checked_file(photo_path(root, capture), root / "captures")
    return FileResponse(path, media_type=capture["media_type"], headers={"Cache-Control": "private"})


def tile_response(root, capture, name):
    directory = root / "work" / capture["id"]
    manifest = read_json(directory / "tiles.json", {})
    entries = manifest.get("tiles", []) if isinstance(manifest, dict) else []
    names = [entry.get("file") for entry in entries if isinstance(entry, dict)] if isinstance(entries, list) else []
    if name not in names or Path(name).name != name or "\\" in name or name in (".", ".."):
        raise HTTPException(404, "the tile was not found")
    # Membership and a plain basename must be established before constructing this path.
    path = checked_file(directory / "tiles" / name, directory / "tiles")
    media_type = MEDIA_TYPES.get(path.suffix.lower())
    if media_type is None:
        raise HTTPException(404, "the tile was not found")
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "private"})
