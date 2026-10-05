"""The stages run on one photo's work directory (see docs/pipeline.md, "Work directory")."""
import json
from pathlib import Path

from home_library.merge import merge_reads


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
