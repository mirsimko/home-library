"""The stages run on one photo's work directory (see docs/pipeline.md, "Work directory")."""
import json
from pathlib import Path

from home_library.lookup import find_candidates
from home_library.lookup.http import Fetcher
from home_library.lookup.nkcr import run_yaz_client
from home_library.merge import merge_reads

LOOKED_UP = ("agreed", "near", "solo")  # a partly read title would only fetch noise


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _store(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return value


def merge_photo(photo_dir, read_ids):
    """Stage 4: compare the two stored reads and write merged.json."""
    photo_dir = Path(photo_dir)
    first, second = (_load(photo_dir / "reads" / read_id / "read.json") for read_id in read_ids)
    return _store(photo_dir / "merged.json", merge_reads(first, second))


def lookup_photo(photo_dir, *, fetch=None, run_yaz=run_yaz_client):
    """Stage 5: fetch catalogue candidates for every fully read title and write candidates.json."""
    photo_dir = Path(photo_dir)
    merged = _load(photo_dir / "merged.json")
    fetch = fetch or Fetcher(photo_dir / "lookup" / "cache")
    books = []
    for index, item in enumerate(merged["items"]):
        if item["reason"] in LOOKED_UP:
            found = find_candidates(item["title"], item["language"], fetch=fetch, run_yaz=run_yaz)
            books.append({"item": index, "title": item["title"], "language": item["language"], **found})
    return _store(photo_dir / "lookup" / "candidates.json", {"file": merged["file"], "books": books})


def gather_read(work_root, read_id):
    """One read's answers for every photo under work_root, in the shape the test-scoring tools take."""
    reads = [_load(path) for path in sorted(Path(work_root).glob(f"*/reads/{read_id}/read.json"))]
    return {"model": read_id, "photos": [{"file": read["file"], "books": read["books"]} for read in reads]}
