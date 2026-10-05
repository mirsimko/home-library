from pathlib import Path

import pytest

from home_library.workspace import DEFAULT_WORK_ROOT, photo_dir


def test_default_work_root_is_home_library_work_in_the_home_directory():
    assert DEFAULT_WORK_ROOT == Path.home() / "home-library" / "work"


def test_photo_dir_is_named_after_the_photo_stem(tmp_path):
    work = tmp_path / "work"
    assert photo_dir(work, Path("/somewhere/else/あかいふうせん.shelf-1.jpg")) == work / "あかいふうせん.shelf-1"


def test_photo_dir_creates_nothing(tmp_path):
    photo_dir(tmp_path / "work", Path("shelf-1.jpg"))
    assert list(tmp_path.iterdir()) == []
