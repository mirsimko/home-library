"""The work directory of a photo (see docs/pipeline.md, "Work directory")."""
from pathlib import Path

DEFAULT_WORK_ROOT = Path.home() / "home-library" / "work"


def refuse_inside_checkout(directory):
    """Raise ValueError when directory (symlinks followed) lies inside a git checkout."""
    directory = Path(directory).resolve()
    for ancestor in [directory, *directory.parents]:
        if (ancestor / ".git").exists():
            raise ValueError(
                f"{directory} lies inside a git checkout ({ancestor}); "
                "run outputs are private and must not land in a repository"
            )
    return directory


def photo_dir(work_root, photo):
    return refuse_inside_checkout(Path(work_root) / Path(photo).stem)
