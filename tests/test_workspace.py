from pathlib import Path

import pytest

from home_library.workspace import DEFAULT_WORK_ROOT, photo_dir


def test_default_work_root_is_home_library_work_in_the_home_directory():
    assert DEFAULT_WORK_ROOT == Path.home() / "home-library" / "work"
