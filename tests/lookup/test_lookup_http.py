import io
import urllib.error

import pytest

from home_library.lookup.http import Fetcher

NDL = "https://ndlsearch.ndl.go.jp/api/opensearch?isbn=9784893094315&dpid=iss-ndl-opac"


class Response:
    def __init__(self, body):
        self.body = body

    def read(self):
        return self.body


class FakeWorld:
    """A fake clock, its sleep, and an opener that answers from a script. No time passes, no network."""

    def __init__(self, *script):
        self.now = 1000.0
        self.sleeps = []
        self.script = list(script)
        self.requests = []  # (url, headers, timeout, time)

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    def opener(self, request, timeout):
        self.requests.append((request.full_url, dict(request.header_items()), timeout, self.now))
        step = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(step, Exception):
            raise step
        return Response(step)

    def fetcher(self, cache_dir=None):
        return Fetcher(cache_dir, opener=self.opener, clock=self.clock, sleep=self.sleep)


def test_fetcher_returns_the_body_and_identifies_itself_with_a_30_second_timeout():
    world = FakeWorld(b"<rss/>")

    body = world.fetcher()(NDL)

    assert body == b"<rss/>"
    url, headers, timeout, _ = world.requests[0]
    assert url == NDL
    assert headers["User-agent"] == "home-library/0.1 (+https://github.com/mirsimko/home-library)"
    assert timeout == 30


def test_a_repeated_call_is_answered_from_the_disk_cache_without_a_request(tmp_path):
    first = FakeWorld(b"answer")
    assert first.fetcher(tmp_path / "cache")(NDL) == b"answer"

    second = FakeWorld(b"a different answer")
    assert second.fetcher(tmp_path / "cache")(NDL) == b"answer"

    assert len(first.requests) == 1
    assert second.requests == []


def test_different_urls_are_cached_separately(tmp_path):
    world = FakeWorld(b"one", b"two")
    fetch = world.fetcher(tmp_path)

    assert fetch(NDL) == b"one"
    assert fetch(NDL + "&cnt=2") == b"two"
    assert fetch(NDL) == b"one"
    assert len(world.requests) == 2


@pytest.mark.parametrize(
    "url, interval",
    [
        (NDL, 1.0),
        ("https://openlibrary.org/search.json?title=x", 1.2),
        ("https://lx2.loc.gov/sru/lcdb?query=x", 0.5),
        ("https://api.openbd.jp/v1/get?isbn=9784001111118", 0.5),
    ],
)
def test_requests_to_one_host_are_spaced_by_that_hosts_minimum_interval(url, interval):
    world = FakeWorld(b"a", b"b")
    fetch = world.fetcher()

    fetch(url)
    fetch(url + "&second=1")

    first, second = world.requests[0][3], world.requests[1][3]
    assert second - first == pytest.approx(interval)


def test_the_first_request_to_a_host_does_not_wait_and_other_hosts_do_not_share_a_pace():
    world = FakeWorld(b"a")
    fetch = world.fetcher()

    fetch(NDL)
    fetch("https://openlibrary.org/search.json?title=x")
    fetch("https://lx2.loc.gov/sru/lcdb?query=x")

    assert world.sleeps == []
