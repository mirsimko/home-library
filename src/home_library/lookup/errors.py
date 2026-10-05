"""Failures of a source. find_candidates records them in the queries; it never lets them escape."""


class SourceError(Exception):
    """A source could not answer: a network failure, a refused search, an unreadable answer."""


class RateLimited(SourceError):
    """The source said it is busy (HTTP 429) and a retry did not help."""


class Unavailable(SourceError):
    """The source cannot be used on this machine, for example yaz-client is not installed."""


class FetchError(SourceError):
    """An HTTP request failed for a reason other than rate limiting."""
