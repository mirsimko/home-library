import io
import threading
import time
import urllib.error
import urllib.request

import urllib.error
import urllib.request

import pytest

from home_library.lookup.errors import FetchError, RateLimited
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


def test_a_second_timeout_is_a_fetch_error_and_not_rate_limiting():
    world = FakeWorld(urllib.error.URLError(TimeoutError("timed out")))

    with pytest.raises(FetchError) as caught:
        world.fetcher()(NDL)

    assert not isinstance(caught.value, RateLimited)
    assert len(world.requests) == 2


@pytest.mark.parametrize("failure", [http_error(500), http_error(404), urllib.error.URLError("refused")])
def test_other_failures_are_fetch_errors_without_a_retry(failure):
    world = FakeWorld(failure)

    with pytest.raises(FetchError) as caught:
        world.fetcher()(NDL)

    assert not isinstance(caught.value, RateLimited)
    assert len(world.requests) == 1


def test_a_failed_request_is_not_cached(tmp_path):
    world = FakeWorld(http_error(500), b"ok")
    fetch = world.fetcher(tmp_path)

    with pytest.raises(FetchError):
        fetch(NDL)

    assert fetch(NDL) == b"ok"


def test_threads_asking_the_same_host_are_served_one_request_at_a_time():
    in_flight, most, opened = [0], [0], [0]
    guard = threading.Lock()

    def slow_opener(request, timeout):
        with guard:
            in_flight[0] += 1
            opened[0] += 1
            most[0] = max(most[0], in_flight[0])
        time.sleep(0.02)  # a real pause inside the fake network, so that overlapping requests would show
        with guard:
            in_flight[0] -= 1
        return Response(b"ok")

    fetch = Fetcher(opener=slow_opener, clock=lambda: 0.0, sleep=lambda seconds: None)
    results, errors = [], []

    def worker(n):
        try:
            results.append(fetch(NDL + "&n=%d" % n))
        except Exception as error:  # collected, because join() does not propagate it
            errors.append(error)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert results == [b"ok"] * 4
    assert opened[0] == 4
    assert most[0] == 1


def test_threads_asking_for_the_same_uncached_url_make_one_request_and_all_succeed(tmp_path):
    calls, results, errors = [], [], []

    def slow_opener(request, timeout):
        calls.append(request.full_url)
        time.sleep(0.05)
        return Response(b"shared")

    fetch = Fetcher(tmp_path, opener=slow_opener, clock=lambda: 0.0, sleep=lambda seconds: None)

    def worker():
        try:
            results.append(fetch(NDL))
        except Exception as error:  # collected, because join() does not propagate it
            errors.append(error)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert results == [b"shared"] * 4
    assert len(calls) == 1
