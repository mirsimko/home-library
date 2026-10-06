"""The real fetch for the HTTP sources: polite, paced and retrying. Standard library only."""
import contextlib
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from home_library.lookup.errors import FetchError, RateLimited, Unavailable

USER_AGENT = "home-library/0.1 (+https://github.com/mirsimko/home-library)"
TIMEOUT_SECONDS = 30
DEFAULT_INTERVAL = 0.5
MIN_INTERVAL = {"ndlsearch.ndl.go.jp": 1.0, "openlibrary.org": 1.2}
RETRY_PAUSE = {"ndlsearch.ndl.go.jp": 25.0}
DEFAULT_RETRY_PAUSE = 5.0


def _urlopen(request, timeout):
    return urllib.request.urlopen(request, timeout=timeout)


class Fetcher:
    def __init__(self, *, opener=None, clock=time.monotonic, sleep=time.sleep):
        self.opener = opener or _urlopen
        self.clock = clock
        self.sleep = sleep
        self.last_request = {}  # host -> clock time of its last request

    def _wait_for_turn(self, host):
        if host in self.last_request:
            wait = self.last_request[host] + MIN_INTERVAL.get(host, DEFAULT_INTERVAL) - self.clock()
            if wait > 0:
                self.sleep(wait)

    def _pause_then_retry(self, url, host, retry, error, failure):
        if not retry:
            raise failure from error
        self.last_request[host] = self.clock()
        self.sleep(RETRY_PAUSE.get(host, DEFAULT_RETRY_PAUSE))
        return self._get(url, host, retry=False)

    def _get(self, url, host, retry):
        self._wait_for_turn(host)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with contextlib.closing(self.opener(request, TIMEOUT_SECONDS)) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code == 429:
                failure = RateLimited("%s answered HTTP 429 twice" % host)
                return self._pause_then_retry(url, host, retry, error, failure)
            raise FetchError("%s answered HTTP %d" % (host, error.code)) from error
        except (TimeoutError, urllib.error.URLError, OSError) as error:
            reason = getattr(error, "reason", error)
            if isinstance(reason, TimeoutError):
                failure = Unavailable("%s timed out twice" % host)
                return self._pause_then_retry(url, host, retry, error, failure)
            raise Unavailable("%s could not be reached: %s" % (host, reason)) from error
        finally:
            self.last_request[host] = self.clock()

    def __call__(self, url):
        return self._get(url, urlparse(url).hostname, retry=True)
