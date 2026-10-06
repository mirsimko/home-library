from urllib.parse import parse_qs, urlparse

import pytest

from home_library.lookup import find_candidates
from home_library.lookup.errors import FetchError, RateLimited, Unavailable


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


def no_http(url):
    raise AssertionError("no HTTP request expected for this language")


def test_english_goes_to_open_library_and_then_the_library_of_congress(fixture_bytes):
    fetch = Router(
        fixture_bytes,
        **{"openlibrary.org": "openlibrary_search_wild_things.json", "lx2.loc.gov": "loc_isbn_9780123456786.xml"},
    )

    result = find_candidates(
        "Where the Wild Things Are", "en", author="Sendak", fetch=fetch, run_yaz=no_yaz
    )

    assert result["queries"] == [
        {"source": "openlibrary", "step": "title+author", "status": "ok", "count": 2},
        {"source": "loc", "step": "title+author", "status": "ok", "count": 1},
    ]
    assert [c["id"] for c in result["candidates"]] == [
        "openlibrary:OL2568879W", "openlibrary:OL2568793W", "loc:2099001234",
    ]


def test_czech_goes_to_nkcr_through_yaz_client_and_uses_no_http(fake_yaz, fixture_bytes):
    run_yaz = fake_yaz(fixture_bytes("nkcr_isbn_9788024297217.txt").decode("utf-8"))

    result = find_candidates("Krtek a zajíček", "cs", isbn="9788024297217", fetch=no_http, run_yaz=run_yaz)

    assert result["queries"] == [{"source": "nkcr", "step": "isbn", "status": "ok", "count": 1}]
    assert result["candidates"][0]["id"] == "nkcr:nkc20233578648"


def test_any_other_language_has_no_source_and_makes_no_request():
    for language in ("zh", "unknown", ""):
        result = find_candidates("Zelený drak", language, fetch=no_http, run_yaz=no_yaz)

        assert result == {"queries": [], "candidates": []}


@pytest.mark.parametrize(
    "title, short_title",
    [
        ("The Very Hungry Caterpillar", "The Very Hungry"),  # more than three words: the first three
        ("あかいふうせんのたび", "あかいふう"),  # no spaces, 10 characters: the first half
        ("あかいふうせ", "あかい"),  # no spaces, exactly 6 characters: the first half
        ("Zelený drak", None),  # two words
        ("The Blue Kite", None),  # exactly three words
        ("あかいふう", None),  # no spaces, 5 characters
    ],
)
def test_the_short_title_step_follows_the_word_and_character_rule(fixture_bytes, title, short_title):
    fetch = Router(fixture_bytes, **{"ndlsearch.ndl.go.jp": "ndl_empty.xml"})

    result = find_candidates(title, "ja", fetch=fetch, run_yaz=no_yaz)

    if short_title is None:
        assert [q["step"] for q in result["queries"]] == ["title"]
    else:
        assert [q["step"] for q in result["queries"]] == ["title", "short-title"]
        assert fetch.params(0)["title"] == title
        assert fetch.params(1)["title"] == short_title
        assert result["queries"][1] == {"source": "ndl", "step": "short-title", "status": "no_match", "count": 0}


def test_at_most_three_requests_are_made_to_one_source_for_one_book(fixture_bytes):
    fetch = Router(
        fixture_bytes, **{"ndlsearch.ndl.go.jp": "ndl_empty.xml", "api.openbd.jp": "openbd_null.json"}
    )

    result = find_candidates(
        "あかいふうせんのたび", "ja", author="山田花子", isbn="9784001111118", fetch=fetch, run_yaz=no_yaz
    )

    ndl_steps = [q["step"] for q in result["queries"] if q["source"] == "ndl"]
    assert ndl_steps == ["isbn", "title+author", "title"]
    assert [q["status"] for q in result["queries"]] == ["no_match"] * 4
    assert len([u for u in fetch.urls if "ndlsearch" in u]) == 3


def test_a_rate_limited_source_is_recorded_and_left_alone_and_the_next_source_still_runs(fixture_bytes):
    def fetch(url):
        if "ndlsearch" in url:
            raise RateLimited("busy")
        return fixture_bytes("openbd_9784001111118.json")

    result = find_candidates(
        "あかいふうせん", "ja", author="山田花子", isbn="9784001111118", fetch=fetch, run_yaz=no_yaz
    )

    assert result["queries"] == [
        {"source": "ndl", "step": "isbn", "status": "rate_limited", "count": 0},
        {"source": "openbd", "step": "isbn", "status": "ok", "count": 1},
    ]
    assert [c["id"] for c in result["candidates"]] == ["openbd:9784001111118"]


def test_a_missing_yaz_client_is_recorded_as_unavailable_and_does_not_raise():
    def run_yaz(commands):
        raise Unavailable("yaz-client is not installed")

    result = find_candidates(
        "Krtek a zajíček", "cs", author="Miler", isbn="9788024297217", fetch=no_http, run_yaz=run_yaz
    )

    assert result == {
        "queries": [{"source": "nkcr", "step": "isbn", "status": "unavailable", "count": 0}],
        "candidates": [],
    }


def test_a_failed_request_is_recorded_as_an_error_and_ends_that_sources_ladder_but_not_the_next_source(
    fixture_bytes,
):
    urls = []

    def fetch(url):
        urls.append(url)
        if "ndlsearch" in url:
            raise FetchError("HTTP 500")
        return fixture_bytes("openbd_9784001111118.json")

    result = find_candidates(
        "だるまさんが", "ja", author="かがくいひろし", isbn="9784001111118", fetch=fetch, run_yaz=no_yaz
    )

    assert result["queries"] == [
        {"source": "ndl", "step": "isbn", "status": "error", "count": 0},
        {"source": "openbd", "step": "isbn", "status": "ok", "count": 1},
    ]
    assert len([u for u in urls if "ndlsearch" in u]) == 1


def test_an_answer_that_cannot_be_read_is_an_error_and_never_raises():
    result = find_candidates("だるま", "ja", fetch=lambda url: b"<html>not what we asked for", run_yaz=no_yaz)

    assert [q["status"] for q in result["queries"]] == ["error"]
    assert result["candidates"] == []


def test_no_more_than_max_per_source_candidates_are_kept_from_each_source(fixture_bytes):
    fetch = Router(fixture_bytes, **{"ndlsearch.ndl.go.jp": "ndl_search_daruma.xml"})

    result = find_candidates("だるまさんが", "ja", fetch=fetch, run_yaz=no_yaz, max_per_source=2)

    assert [c["id"] for c in result["candidates"]] == ["ndl:000009209109", "ndl:025053389"]
    assert result["queries"][0]["count"] == 2


def test_a_record_that_a_source_returns_twice_is_kept_once(fixture_bytes):
    text = fixture_bytes("ndl_search_daruma.xml").decode("utf-8")
    first_item = text[text.index("<item>"): text.index("</item>") + len("</item>")]
    doubled = text.replace(first_item, first_item + first_item, 1).encode("utf-8")

    result = find_candidates("だるまさんが", "ja", fetch=lambda url: doubled, run_yaz=no_yaz)

    ids = [c["id"] for c in result["candidates"]]
    assert ids == ["ndl:000009209109", "ndl:025053389", "ndl:000011170599"]
    assert result["queries"][0]["count"] == 3


def test_records_a_source_gives_no_id_are_all_kept_and_told_apart_by_a_number():
    answer = b'{"docs": [{"title": "Blue Kite"}, {"key": "/works/OL1W", "title": "Blue Kite"}, {"title": "Kite"}]}'

    result = find_candidates(
        "Blue Kite", "en", fetch=lambda url: answer if "openlibrary" in url else b"", run_yaz=no_yaz
    )

    found = [(c["id"], c["source_id"], c["title"]) for c in result["candidates"]]
    assert found == [
        ("openlibrary:no-id-1", "", "Blue Kite"),
        ("openlibrary:OL1W", "OL1W", "Blue Kite"),
        ("openlibrary:no-id-2", "", "Kite"),
    ]


def test_a_step_that_ran_before_is_answered_from_the_cache_and_recorded_as_if_it_had_run(fixture_bytes, tmp_path):
    fetch = Router(fixture_bytes, **{"ndlsearch.ndl.go.jp": "ndl_search_daruma.xml"})
    first = find_candidates("だるまさんが", "ja", fetch=fetch, run_yaz=no_yaz, cache_dir=tmp_path / "cache")

    second = find_candidates("だるまさんが", "ja", fetch=no_http, run_yaz=no_yaz, cache_dir=tmp_path / "cache")

    assert second == first
    assert second["queries"] == [{"source": "ndl", "step": "title", "status": "ok", "count": 3}]
    assert [c["id"] for c in second["candidates"]] == [
        "ndl:000009209109", "ndl:025053389", "ndl:000011170599",
    ]


def test_an_empty_answer_is_cached_too_because_no_match_is_an_answer(fixture_bytes, tmp_path):
    fetch = Router(fixture_bytes, **{"ndlsearch.ndl.go.jp": "ndl_empty.xml"})
    find_candidates("Zelený drak", "ja", fetch=fetch, run_yaz=no_yaz, cache_dir=tmp_path)

    second = find_candidates("Zelený drak", "ja", fetch=no_http, run_yaz=no_yaz, cache_dir=tmp_path)

    assert second["queries"] == [{"source": "ndl", "step": "title", "status": "no_match", "count": 0}]


def test_a_step_that_failed_is_not_cached(fixture_bytes, tmp_path):
    def broken(url):
        raise FetchError("HTTP 500")

    find_candidates("だるまさんが", "ja", fetch=broken, run_yaz=no_yaz, cache_dir=tmp_path)
    fetch = Router(fixture_bytes, **{"ndlsearch.ndl.go.jp": "ndl_search_daruma.xml"})

    second = find_candidates("だるまさんが", "ja", fetch=fetch, run_yaz=no_yaz, cache_dir=tmp_path)

    assert second["queries"] == [{"source": "ndl", "step": "title", "status": "ok", "count": 3}]
    assert len(fetch.urls) == 1


def test_a_step_is_cached_by_its_query_values(fixture_bytes, tmp_path):
    fetch = Router(fixture_bytes, **{"ndlsearch.ndl.go.jp": "ndl_search_daruma.xml"})
    find_candidates("だるまさんが", "ja", fetch=fetch, run_yaz=no_yaz, cache_dir=tmp_path)

    find_candidates("あかいふうせん", "ja", fetch=fetch, run_yaz=no_yaz, cache_dir=tmp_path)
    find_candidates("だるまさんが", "ja", author="山田花子", fetch=fetch, run_yaz=no_yaz, cache_dir=tmp_path)

    assert [fetch.params(i).get("title") for i in range(3)] == ["だるまさんが", "あかいふうせん", "だるまさんが"]
    assert "creator" in fetch.params(2)


def test_nkcr_answers_are_cached_too(fake_yaz, fixture_bytes, tmp_path):
    run_yaz = fake_yaz(fixture_bytes("nkcr_isbn_9788024297217.txt").decode("utf-8"))
    first = find_candidates(
        "Krtek a zajíček", "cs", isbn="9788024297217", fetch=no_http, run_yaz=run_yaz, cache_dir=tmp_path
    )

    second = find_candidates(
        "Krtek a zajíček", "cs", isbn="9788024297217", fetch=no_http, run_yaz=no_yaz, cache_dir=tmp_path
    )

    assert second == first
    assert len(run_yaz.scripts) == 1


def test_the_cache_directory_is_created_on_the_first_write_and_leaves_only_finished_files(fixture_bytes, tmp_path):
    cache = tmp_path / "lookup" / "cache"
    fetch = Router(fixture_bytes, **{"ndlsearch.ndl.go.jp": "ndl_search_daruma.xml"})

    find_candidates("だるまさんが", "ja", fetch=fetch, run_yaz=no_yaz, cache_dir=cache)

    names = [path.name for path in cache.iterdir()]
    assert len(names) == 1
    assert names[0].endswith(".json")


def test_a_skipped_source_is_not_called_and_is_recorded_as_unavailable(fixture_bytes):
    fetch = Router(fixture_bytes, **{"api.openbd.jp": "openbd_9784001111118.json"})

    result = find_candidates(
        "あかいふうせん", "ja", author="山田花子", isbn="9784001111118", fetch=fetch, run_yaz=no_yaz, skip={"ndl"}
    )

    assert result["queries"] == [
        {"source": "ndl", "step": "skipped", "status": "unavailable", "count": 0},
        {"source": "openbd", "step": "isbn", "status": "ok", "count": 1},
    ]
    assert [c["id"] for c in result["candidates"]] == ["openbd:9784001111118"]
    assert [urlparse(u).hostname for u in fetch.urls] == ["api.openbd.jp"]


def test_a_skipped_nkcr_does_not_run_yaz_client():
    result = find_candidates("Zelený drak", "cs", fetch=no_http, run_yaz=no_yaz, skip=["nkcr"])

    assert result == {
        "queries": [{"source": "nkcr", "step": "skipped", "status": "unavailable", "count": 0}],
        "candidates": [],
    }


@pytest.mark.parametrize("language, source", [("JA", "ndl"), (" cs ", "nkcr"), ("En\n", "openlibrary")])
def test_the_language_is_matched_ignoring_case_and_surrounding_whitespace(language, source):
    def fetch(url):
        raise FetchError("HTTP 500")

    def run_yaz(commands):
        raise FetchError("failed")

    result = find_candidates("Zelený drak", language, fetch=fetch, run_yaz=run_yaz)

    assert result["queries"][0]["source"] == source


def test_a_language_that_is_not_ja_cs_or_en_still_gets_no_source_after_cleaning():
    assert find_candidates("Zelený drak", " ZH ", fetch=no_http, run_yaz=no_yaz) == {"queries": [], "candidates": []}


def test_a_missing_language_gets_no_source_and_does_not_raise():
    assert find_candidates("Zelený drak", None, fetch=no_http, run_yaz=no_yaz) == {"queries": [], "candidates": []}
