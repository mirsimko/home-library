"""The real fetch for the HTTP sources: polite, paced, retrying and cached. Standard library only."""
import hashlib
import os
import urllib.request
from pathlib import Path

USER_AGENT = "home-library/0.1 (+https://github.com/mirsimko/home-library)"
TIMEOUT_SECONDS = 30


class Fetcher:
    def __init__(self, cache_dir=None, *, opener=urllib.request.urlopen, clock=None, sleep=None):
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.opener = opener

    def _cache_path(self, url):
        return self.cache_dir / hashlib.sha256(url.encode("utf-8")).hexdigest()

    def __call__(self, url):
        if self.cache_dir is not None and self._cache_path(url).exists():
            return self._cache_path(url).read_bytes()
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        body = self.opener(request, TIMEOUT_SECONDS).read()
        if self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            partial = self._cache_path(url).with_suffix(".part")
            partial.write_bytes(body)
            os.replace(partial, self._cache_path(url))
        return body
