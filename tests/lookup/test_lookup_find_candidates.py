from urllib.parse import parse_qs, urlparse

from home_library.lookup import find_candidates


class Router:
    """A fake fetch that answers by host and by whether a query parameter is present."""

    def __init__(self, fixture_bytes, **routes):
        self.fixture_bytes = fixture_bytes
        self.routes = routes  # host -> fixture name, or {param: fixture name, None: default fixture name}
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        parts = urlparse(url)
        route = self.routes[parts.hostname]
        if isinstance(route, dict):
            params = parse_qs(parts.query)
            for key, name in route.items():
                if key is not None and key in params:
                    return self.fixture_bytes(name)
            return self.fixture_bytes(route[None])
        return self.fixture_bytes(route)

    def params(self, index):
        return {k: v[0] for k, v in parse_qs(urlparse(self.urls[index]).query).items()}


def no_yaz(commands):
    raise AssertionError("yaz-client must not be used for this language")


def test_a_japanese_title_is_searched_in_ndl_and_the_step_is_recorded(fixture_bytes):
    fetch = Router(fixture_bytes, **{"ndlsearch.ndl.go.jp": "ndl_search_daruma.xml"})

    result = find_candidates("だるまさんが", "ja", fetch=fetch, run_yaz=no_yaz)

    assert result["queries"] == [{"source": "ndl", "step": "title", "status": "ok", "count": 3}]
    assert [c["id"] for c in result["candidates"]] == [
        "ndl:000009209109", "ndl:025053389", "ndl:000011170599",
    ]
    assert len(fetch.urls) == 1
