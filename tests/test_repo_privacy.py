"""The repository is public; photos of the home and run outputs must never be tracked."""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".heic", ".webp", ".gif", ".tif", ".tiff"}
PRIVATE_DIRS = {"samples", "work"}


def tracked_files():
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO, check=True, capture_output=True, text=True
    ).stdout
    return [Path(p) for p in out.split("\0") if p]


def test_no_image_is_tracked():
    images = [p for p in tracked_files() if p.suffix.lower() in IMAGE_SUFFIXES]
    assert images == []


def test_no_private_directory_is_tracked():
    private = [p for p in tracked_files() if p.parts[0] in PRIVATE_DIRS]
    assert private == []
