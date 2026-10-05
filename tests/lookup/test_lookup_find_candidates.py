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


def test_a_valid_isbn_is_tried_first_in_ndl_and_then_in_openbd_and_the_ladder_stops(fixture_bytes):
    fetch = Router(
        fixture_bytes,
        **{"ndlsearch.ndl.go.jp": "ndl_isbn_9784893094315.xml", "api.openbd.jp": "openbd_9784001111118.json"},
    )

    result = find_candidates(
        "だるまさんが", "ja", author="かがくいひろし", isbn="978-4-89309-431-5", fetch=fetch, run_yaz=no_yaz
    )

    assert result["queries"] == [
        {"source": "ndl", "step": "isbn", "status": "ok", "count": 2},
        {"source": "openbd", "step": "isbn", "status": "ok", "count": 1},
    ]
    assert [c["source"] for c in result["candidates"]] == ["ndl", "ndl", "openbd"]
    assert len(fetch.urls) == 2
    assert fetch.params(0)["isbn"] == "9784893094315"
    assert fetch.params(1)["isbn"] == "9784893094315"


def test_an_invalid_isbn_is_not_used(fixture_bytes):
    fetch = Router(fixture_bytes, **{"ndlsearch.ndl.go.jp": "ndl_search_daruma.xml"})

    result = find_candidates("だるまさんが", "ja", isbn="9784893094316", fetch=fetch, run_yaz=no_yaz)

    assert [q["step"] for q in result["queries"]] == ["title"]


def test_with_an_author_the_ladder_goes_from_title_and_author_to_the_title_alone(fixture_bytes):
    fetch = Router(
        fixture_bytes,
        **{"ndlsearch.ndl.go.jp": {"creator": "ndl_empty.xml", None: "ndl_search_daruma.xml"}},
    )

    result = find_candidates("だるまさんが", "ja", author="かがくいひろし", fetch=fetch, run_yaz=no_yaz)

    assert result["queries"] == [
        {"source": "ndl", "step": "title+author", "status": "no_match", "count": 0},
        {"source": "ndl", "step": "title", "status": "ok", "count": 3},
    ]
    assert fetch.params(0)["creator"] == "かがくいひろし"
    assert "creator" not in fetch.params(1)


def test_the_ladder_stops_at_the_first_step_that_returns_candidates(fixture_bytes):
    fetch = Router(fixture_bytes, **{"ndlsearch.ndl.go.jp": "ndl_search_daruma.xml"})

    result = find_candidates("だるまさんが", "ja", author="かがくいひろし", fetch=fetch, run_yaz=no_yaz)

    assert [q["step"] for q in result["queries"]] == ["title+author"]
    assert len(fetch.urls) == 1
