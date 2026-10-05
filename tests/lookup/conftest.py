from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


class FakeFetch:
    """A stand-in for the real fetch: returns canned bytes and remembers the URLs."""

    def __init__(self, *bodies):
        self.bodies = list(bodies)
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        body = self.bodies.pop(0) if len(self.bodies) > 1 else self.bodies[0]
        if isinstance(body, Exception):
            raise body
        return body

    def query(self, index=-1):
        """The query parameters of one recorded URL, as a dict of single values."""
        return {k: v[0] for k, v in parse_qs(urlparse(self.urls[index]).query).items()}


@pytest.fixture
def fixture_bytes():
    return lambda name: (FIXTURES / name).read_bytes()


@pytest.fixture
def fake_fetch():
    return FakeFetch
