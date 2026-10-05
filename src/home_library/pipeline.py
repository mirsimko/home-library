"""The stages run on one photo's work directory (see docs/pipeline.md, "Work directory")."""
import json
import subprocess
from pathlib import Path

from home_library.lookup import find_candidates
from home_library.lookup.http import Fetcher
from home_library.lookup.nkcr import run_yaz_client
from home_library.merge import merge_reads
from home_library.pick import run_pick
from home_library.reader import run_read
from home_library.records import build_records, write_records
from home_library.tiles import cut_tiles
from home_library.workspace import DEFAULT_WORK_ROOT, photo_dir as photo_dir_of

READERS = (("a-sol", "codex-exec"), ("b-spark", "pi"))  # read id and backend of the two blind reads

LOOKED_UP = ("agreed", "near", "split", "solo")  # a partly read title would only fetch noise


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


def export_photo(photo_dir, *, location=""):
    """Stage 6: write records.json and records.csv from whatever the earlier stages left."""
    photo_dir = Path(photo_dir)
    lookup_dir = photo_dir / "lookup"
    candidates = _load(lookup_dir / "candidates.json") if (lookup_dir / "candidates.json").exists() else None
    picks = _load(lookup_dir / "picks.json") if (lookup_dir / "picks.json").exists() else None
    records = build_records(_load(photo_dir / "merged.json"), candidates, picks, location=location)
    write_records(photo_dir, records)
    return records


def run_photo(photo, work_root=DEFAULT_WORK_ROOT, *, readers=READERS, location="",
              run=subprocess.run, fetch=None, run_yaz=run_yaz_client):
    """Every stage for one photo, the two reads one after the other. Returns a short summary."""
    photo_dir = photo_dir_of(work_root, photo)
    cut_tiles(photo, photo_dir)
    for read_id, backend in readers:
        run_read(photo_dir, read_id, backend, run=run)
    merged = merge_photo(photo_dir, [read_id for read_id, _ in readers])
    lookup_photo(photo_dir, fetch=fetch, run_yaz=run_yaz)
    run_pick(photo_dir, run=run)
    export_photo(photo_dir, location=location)
    statuses = [item["status"] for item in merged["items"]]
    return {"photo": merged["file"], "directory": str(photo_dir),
            "accepted": statuses.count("accepted"), "review": statuses.count("review"),
            "unreadable": sum(1 for entry in merged["unreadable"] if entry["read_id"] == readers[0][0])}
