"""The real fetch for the HTTP sources: polite, paced, retrying and cached. Standard library only."""
import hashlib
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from home_library.lookup.errors import RateLimited

USER_AGENT = "home-library/0.1 (+https://github.com/mirsimko/home-library)"
TIMEOUT_SECONDS = 30
DEFAULT_INTERVAL = 0.5
MIN_INTERVAL = {"ndlsearch.ndl.go.jp": 1.0, "openlibrary.org": 1.2}
RETRY_PAUSE = {"ndlsearch.ndl.go.jp": 25.0}
DEFAULT_RETRY_PAUSE = 5.0


class Fetcher:
    def __init__(self, cache_dir=None, *, opener=urllib.request.urlopen, clock=time.monotonic, sleep=time.sleep):
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.opener = opener
        self.clock = clock
        self.sleep = sleep
        self.last_request = {}  # host -> clock time of its last request

    def _cache_path(self, url):
        return self.cache_dir / hashlib.sha256(url.encode("utf-8")).hexdigest()

    def _wait_for_turn(self, host):
        if host in self.last_request:
            wait = self.last_request[host] + MIN_INTERVAL.get(host, DEFAULT_INTERVAL) - self.clock()
            if wait > 0:
                self.sleep(wait)

    def _get(self, url, host, retry):
        self._wait_for_turn(host)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            return self.opener(request, TIMEOUT_SECONDS).read()
        except urllib.error.HTTPError as error:
            if error.code != 429:
                raise
            if not retry:
                raise RateLimited("%s answered HTTP 429 twice" % host) from error
            self.last_request[host] = self.clock()
            self.sleep(RETRY_PAUSE.get(host, DEFAULT_RETRY_PAUSE))
            return self._get(url, host, retry=False)
        finally:
            self.last_request[host] = self.clock()

    def __call__(self, url):
        if self.cache_dir is not None and self._cache_path(url).exists():
            return self._cache_path(url).read_bytes()
        host = urlparse(url).hostname
        body = self._get(url, host, retry=True)
        if self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            partial = self._cache_path(url).with_suffix(".part")
            partial.write_bytes(body)
            os.replace(partial, self._cache_path(url))
        return body
