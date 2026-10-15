"""Read printed barcodes from a photo, keeping the decoded evidence for review."""
from pathlib import Path

import zxingcpp
from PIL import Image, ImageOps

from home_library.lookup import find_candidates
from home_library.lookup.isbn import normalize_isbn


def decode_photo(photo, *, decode=zxingcpp.read_barcodes):
    """Keep every decoded code and select the first EAN-13 with a valid ISBN prefix and check digit."""
    photo = Path(photo)
    with Image.open(photo) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    codes = [{"format": str(code.format), "text": code.text} for code in decode(image)]
    isbn = next((code["text"] for code in codes
                 if code["format"] == "EAN-13" and len(code["text"]) == 13
                 and code["text"].startswith(("978", "979")) and normalize_isbn(code["text"])), None)
    return {"file": photo.name, "codes": codes, "isbn": isbn}


def lookup_isbn(isbn, *, fetch, run_yaz, cache_dir):
    """Look up only the ISBN, using its registration group or trying the three supported languages."""
    groups = (("9784", "ja"), ("97880", "cs"), ("9780", "en"), ("9781", "en"), ("9798", "en"))
    language = next((language for prefix, language in groups if isbn.startswith(prefix)), "unknown")
    queries = []
    for tried in ([language] if language != "unknown" else ["ja", "cs", "en"]):
        found = find_candidates("", tried, isbn=isbn, fetch=fetch, run_yaz=run_yaz, cache_dir=cache_dir)
        queries.extend(found["queries"])
        if found["candidates"]:
            return {**found, "queries": queries, "language": tried}
    return {"queries": queries, "candidates": [], "language": language}
