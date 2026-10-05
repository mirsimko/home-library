"""The stages run on one photo's work directory (see docs/pipeline.md, "Work directory")."""
import hashlib
import json
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from home_library.lookup import find_candidates
from home_library.lookup.http import Fetcher
from home_library.lookup.nkcr import run_yaz_client
from home_library.merge import merge_reads
from home_library.pick import run_pick, stored_picks
from home_library.reader import run_read
from home_library.records import build_records, write_records
from home_library.tiles import cut_tiles
from home_library.workspace import DEFAULT_WORK_ROOT, photo_dir as photo_dir_of, refuse_inside_checkout

READERS = (("a-sol", "codex-exec"), ("b-spark", "pi"))  # read id and backend of the two blind reads

LOOKED_UP = ("agreed", "near", "split", "solo")  # a partly read title would only fetch noise


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_or_none(path):
    """A stored file, or None when it is missing or was cut short by a killed run."""
    try:
        return _load(path)
    except (OSError, ValueError):
        return None


def _store(path, value):
    path = Path(path)
    refuse_inside_checkout(path.parent)
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
    fetch = fetch or Fetcher()
    books, down = [], set()  # a source that could not be reached is not asked again for this photo
    for index, item in enumerate(merged["items"]):
        if item["reason"] in LOOKED_UP:
            found = find_candidates(item["title"], item["language"], fetch=fetch, run_yaz=run_yaz,
                                    cache_dir=photo_dir / "lookup" / "cache", skip=down)
            down.update(query["source"] for query in found["queries"]
                        if query["status"] in ("unavailable", "rate_limited"))
            books.append({"item": index, "title": item["title"], "language": item["language"], **found})
    return _store(photo_dir / "lookup" / "candidates.json", {"file": merged["file"], "books": books})


def gather_read(work_root, read_id):
    """One read's answers for every photo under work_root, in the shape the test-scoring tools take."""
    reads = [_load(path) for path in sorted(Path(work_root).glob(f"*/reads/{read_id}/read.json"))]
    return {"model": read_id, "photos": [{"file": read["file"], "books": read["books"]} for read in reads]}


def export_photo(photo_dir, *, location=""):
    """Stage 6: write records.json and records.csv from whatever the earlier stages left."""
    photo_dir = Path(photo_dir)
    merged = _load(photo_dir / "merged.json")
    candidates = _load_or_none(photo_dir / "lookup" / "candidates.json")
    picks = stored_picks(photo_dir, merged, candidates) if candidates else None  # never a pick for other readings
    records = build_records(merged, candidates, picks, location=location)
    write_records(photo_dir, records)
    return records


DERIVED = ("merged.json", "records.json", "records.csv", "lookup/candidates.json", "lookup/picks.json",
           "lookup/picks.raw.txt")


def _manifest_of(photo, photo_dir):
    """The stored tile manifest if it is of this very photo file, else None."""
    manifest = _load_or_none(photo_dir / "tiles.json")
    same = manifest is not None and manifest.get("sha256") == hashlib.sha256(Path(photo).read_bytes()).hexdigest()
    return manifest if same else None


def read_photo(photo, work_root=DEFAULT_WORK_ROOT, *, readers=READERS, force=False, run=subprocess.run):
    """Stages 1 to 4 for one photo: tiles, the reads (at the same time) and the merge. Returns its directory.

    A read that is already stored is not repeated, so a run that failed half way can simply be started again.
    A changed photo, or force, starts from nothing: every file made from the old photo is removed first.
    """
    photo_dir = photo_dir_of(work_root, photo)
    manifest = None if force else _manifest_of(photo, photo_dir)
    if manifest is None:
        shutil.rmtree(photo_dir / "reads", ignore_errors=True)
        for name in DERIVED:
            (photo_dir / name).unlink(missing_ok=True)
    if manifest is None or not all((photo_dir / "tiles" / tile["file"]).is_file() for tile in manifest["tiles"]):
        cut_tiles(photo, photo_dir)
    tiles = hashlib.sha256((photo_dir / "tiles.json").read_bytes()).hexdigest()
    missing = [reader for reader in readers  # not stored, cut short, or made from other tiles
               if (_load_or_none(photo_dir / "reads" / reader[0] / "read.json") or {}).get("tiles_sha256") != tiles]
    # Both reads at once: measured on the home uplink, this took no longer than the slower read alone.
    with ThreadPoolExecutor(max_workers=len(readers)) as pool:
        reads = [pool.submit(run_read, photo_dir, read_id, backend, run=run) for read_id, backend in missing]
    for read in reads:
        read.result()  # raises the read's failure, after every read has ended
    merge_photo(photo_dir, [read_id for read_id, _ in readers])
    return photo_dir


def finish_photo(photo_dir, *, readers=READERS, location="", run=subprocess.run, fetch=None,
                 run_yaz=run_yaz_client):
    """Stages 5 and 6 for one photo: look-up, pick and records. Returns a short summary."""
    photo_dir = Path(photo_dir)
    merged = _load(photo_dir / "merged.json")
    candidates = lookup_photo(photo_dir, fetch=fetch, run_yaz=run_yaz)
    picks = stored_picks(photo_dir, merged, candidates)
    if picks is None or picks["failed"]:  # made for other readings or candidates, or the model call failed
        run_pick(photo_dir, run=run)
    records = export_photo(photo_dir, location=location)
    statuses = [record["read_status"] for record in records]
    accepted = statuses.count("agreed")
    return {"photo": merged["file"], "directory": str(photo_dir),
            "accepted": accepted, "review": len(merged["items"]) - accepted,
            "unreadable": statuses.count("unreadable"),
            "warnings": statuses.count("unparsed") + statuses.count("incomplete"),
            "seconds": {read_id: float(_load(photo_dir / "reads" / read_id / "run.json")["seconds"])
                        for read_id, _ in readers}}


def _failure(photo, failure):
    return {"photo": Path(photo).name, "error": f"{type(failure).__name__}: {failure}"}


def run_photos(photos, work_root=DEFAULT_WORK_ROOT, *, readers=READERS, location="", force=False,
               run=subprocess.run, fetch=None, run_yaz=run_yaz_client, report=lambda result: None):
    """Every stage for several photos. Returns one summary per photo, or its error.

    Photos are read one after another, because the uplink carries one photo's images at a time. The look-ups
    of a photo run in the background while the next photo is read: one NDL title search takes 10 to 15 seconds.
    A photo that fails does not stop the others. `report` is called with each result as soon as it is final.
    """
    results = [None] * len(photos)
    fetch = fetch or Fetcher()  # one for the whole run, so the pacing of a source holds across photos

    def finish(index, photo, photo_dir):
        try:
            results[index] = finish_photo(photo_dir, readers=readers, location=location, run=run,
                                          fetch=fetch, run_yaz=run_yaz)
        except Exception as failure:
            results[index] = _failure(photo, failure)
        report(results[index])

    seen = set()
    with ThreadPoolExecutor(max_workers=1) as background:  # one look-up at a time: the sources are paced
        for index, photo in enumerate(photos):
            try:
                if Path(photo).stem in seen:  # it would share, and overwrite, the other photo's work directory
                    raise ValueError("another photo in this run has the same file name; rename one of them")
                seen.add(Path(photo).stem)
                photo_dir = read_photo(photo, work_root, readers=readers, force=force, run=run)
            except Exception as failure:
                results[index] = _failure(photo, failure)
                report(results[index])
                continue
            background.submit(finish, index, photo, photo_dir)
    return results
