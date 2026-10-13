"""Temporary private data and generated uploads for HTTP tests."""
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from home_library.web import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path, [], dev_user="parent"),
                    headers={"Sec-Fetch-Site": "same-origin"}) as client:
        yield client


def photo(format="JPEG", size=(4080, 3072), orientation=None):
    output = BytesIO()
    exif = Image.Exif()
    if orientation is not None:
        exif[274] = orientation
    Image.new("RGB", size, "white").save(output, format, exif=exif)
    return output.getvalue()
