from home_library.lookup import openbd


def test_openbd_by_isbn_returns_the_candidate_in_the_contract_shape(fake_fetch, fixture_bytes):
    fetch = fake_fetch(fixture_bytes("openbd_9784001111118.json"))

    candidates = openbd.by_isbn("9784001111118", fetch)

    assert candidates == [
        {
            "id": "openbd:9784001111118",
            "source": "openbd",
            "source_id": "9784001111118",
            "url": "https://api.openbd.jp/v1/get?isbn=9784001111118",
            "title": "あかいふうせん",
            "title_reading": "アカイ フウセン",
            "authors": ["山田,花子"],
            "publisher": "たんぽぽ書房",
            "year": "2020",
            "isbn": "9784001111118",
            "series": "ふうせんえほん",
            "language": "ja",
            "audience": "",
            "age_note": "",
            "subjects": [],
            "summary": "空へのぼっていくあかいふうせんのおはなし。",
        }
    ]
    assert fetch.urls[0].startswith("https://api.openbd.jp/v1/get?")
    assert fetch.query()["isbn"] == "9784001111118"


def test_openbd_answers_null_for_an_isbn_it_does_not_hold(fake_fetch, fixture_bytes):
    fetch = fake_fetch(fixture_bytes("openbd_null.json"))

    assert openbd.by_isbn("9784001111118", fetch) == []
