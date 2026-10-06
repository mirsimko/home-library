import urllib.error
import urllib.request

import pytest

from home_library.lookup.errors import FetchError, RateLimited, Unavailable
from home_library.lookup.http import Fetcher

NDL = "https://ndlsearch.ndl.go.jp/api/opensearch?isbn=9784893094315&dpid=iss-ndl-opac"


class Response:
    def __init__(self, body):
        self.body = body
        self.closed = False

    def read(self):
        return self.body

    def close(self):
        self.closed = True


class FakeWorld:
    """A fake clock, its sleep, and an opener that answers from a script. No time passes, no network."""

    def __init__(self, *script):
        self.now = 1000.0
        self.sleeps = []
        self.script = list(script)
        self.requests = []  # (url, headers, timeout, time)
        self.responses = []

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
        self.responses.append(Response(step))
        return self.responses[-1]

    def fetcher(self):
        return Fetcher(opener=self.opener, clock=self.clock, sleep=self.sleep)


def test_fetcher_returns_the_body_and_identifies_itself_with_a_30_second_timeout():
    world = FakeWorld(b"<rss/>")

    body = world.fetcher()(NDL)

    assert body == b"<rss/>"
    url, headers, timeout, _ = world.requests[0]
    assert url == NDL
    assert headers["User-agent"] == "home-library/0.1 (+https://github.com/mirsimko/home-library)"
    assert timeout == 30


def test_fetcher_closes_the_response_once_it_is_read():
    world = FakeWorld(b"<rss/>")

    world.fetcher()(NDL)

    assert [response.closed for response in world.responses] == [True]


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


def http_error(code):
    return urllib.error.HTTPError("https://example.test/", code, "error", {}, None)


def test_a_429_from_ndl_is_retried_once_after_a_25_second_pause():
    world = FakeWorld(http_error(429), b"ok")

    body = world.fetcher()(NDL)

    assert body == b"ok"
    assert len(world.requests) == 2
    assert world.requests[1][3] - world.requests[0][3] == pytest.approx(25)


def test_a_429_from_another_host_is_retried_once_after_a_shorter_pause():
    world = FakeWorld(http_error(429), b"ok")

    world.fetcher()("https://openlibrary.org/search.json?title=x")

    assert 1.2 <= world.requests[1][3] - world.requests[0][3] <= 10


def test_a_second_429_is_reported_as_rate_limited_after_two_requests():
    world = FakeWorld(http_error(429))

    with pytest.raises(RateLimited):
        world.fetcher()(NDL)

    assert len(world.requests) == 2


def test_a_timeout_is_retried_once_after_a_pause():
    world = FakeWorld(TimeoutError("timed out"), b"ok")

    assert world.fetcher()(NDL) == b"ok"

    assert world.requests[1][3] - world.requests[0][3] == pytest.approx(25)


def test_a_second_timeout_makes_the_host_unavailable_and_not_rate_limited():
    world = FakeWorld(urllib.error.URLError(TimeoutError("timed out")))

    with pytest.raises(Unavailable) as caught:
        world.fetcher()(NDL)

    assert not isinstance(caught.value, RateLimited)
    assert len(world.requests) == 2


def test_a_host_that_cannot_be_reached_is_unavailable_without_a_retry():
    world = FakeWorld(urllib.error.URLError("refused"))

    with pytest.raises(Unavailable):
        world.fetcher()(NDL)

    assert len(world.requests) == 1


@pytest.mark.parametrize("failure", [http_error(500), http_error(404)])
def test_an_http_error_status_other_than_429_is_a_fetch_error_without_a_retry(failure):
    world = FakeWorld(failure)

    with pytest.raises(FetchError) as caught:
        world.fetcher()(NDL)

    assert not isinstance(caught.value, (RateLimited, Unavailable))
    assert len(world.requests) == 1


def test_the_default_opener_calls_urlopen_with_the_timeout_and_no_request_body(monkeypatch):
    calls = []

    def fake_urlopen(request, *args, **kwargs):
        calls.append((request.full_url, args, kwargs))
        return Response(b"live")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    assert Fetcher()(NDL) == b"live"

    assert calls == [(NDL, (), {"timeout": 30})]
