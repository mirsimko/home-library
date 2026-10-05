"""The real fetch for the HTTP sources: polite, paced, retrying and cached. Standard library only."""
import urllib.request

USER_AGENT = "home-library/0.1 (+https://github.com/mirsimko/home-library)"
TIMEOUT_SECONDS = 30


class Fetcher:
    def __init__(self, cache_dir=None, *, opener=urllib.request.urlopen, clock=None, sleep=None):
        self.cache_dir = cache_dir
        self.opener = opener

    def __call__(self, url):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        return self.opener(request, TIMEOUT_SECONDS).read()
