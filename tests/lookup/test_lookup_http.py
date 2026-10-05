import io
import urllib.error

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
