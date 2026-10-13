import json
from types import SimpleNamespace

import pytest
from barcode_helpers import ean13
from PIL import Image


def test_generated_bars_are_decoded_by_zxing_cpp():
    import zxingcpp

    (code,) = zxingcpp.read_barcodes(ean13("9784000000000"))
    assert code.format == zxingcpp.BarcodeFormat.EAN13
    assert code.text == "9784000000000"


def test_a_barcode_photo_is_transposed_before_decoding_and_keeps_all_codes(tmp_path):
    import zxingcpp

    from home_library.barcode import decode_photo

    image = Image.new("RGB", (476, 600), "white")
    image.paste(ean13("4000000000006"), (0, 0))
    image.paste(ean13("9784000000000"), (0, 300))
    exif = Image.Exif()
    exif[274] = 6
    photo = tmp_path / "barcode.jpg"
    image.rotate(90, expand=True).save(photo, exif=exif)
    seen = []

    def decode(upright):
        seen.append(upright.size)
        return zxingcpp.read_barcodes(upright, try_rotate=False)

    result = decode_photo(photo, decode=decode)

    assert seen == [(476, 600)]
    assert result["file"] == "barcode.jpg"
    assert result["codes"] == [{"format": "EAN-13", "text": "4000000000006"},
                               {"format": "EAN-13", "text": "9784000000000"}]
    assert result["isbn"] == "9784000000000"


@pytest.mark.parametrize("text", [None, "4000000000006", "9784000000001"])
def test_no_isbn_is_selected_from_a_blank_photo_a_product_code_or_bad_check_digit(tmp_path, text):
    from home_library.barcode import decode_photo

    photo = tmp_path / "barcode.png"
    (ean13(text) if text else Image.new("RGB", (476, 280), "white")).save(photo)
    result = decode_photo(photo)
    assert result["isbn"] is None
    assert result["codes"] == ([{"format": "EAN-13", "text": text}] if text == "4000000000006" else [])


def test_only_the_first_valid_isbn_in_an_ean13_code_is_selected(tmp_path):
    from home_library.barcode import decode_photo

    photo = tmp_path / "barcode.png"
    Image.new("RGB", (20, 20), "white").save(photo)
    codes = [SimpleNamespace(format=kind, text=text) for kind, text in (
        ("QR Code", "9784000000000"), ("EAN-13", "9784000000001"), ("EAN-13", "4000000000006"),
        ("EAN-13", "9798000000007"), ("EAN-13", "9780000000002"))]
    result = decode_photo(photo, decode=lambda image: codes)
    assert result["isbn"] == "9798000000007"
    assert len(result["codes"]) == 5


def test_a_barcode_photo_with_no_isbn_writes_a_row_asking_for_the_number(tmp_path):
    from home_library.pipeline import barcode_photo

    for name, image, codes in (("blank", Image.new("RGB", (476, 280), "white"), []),
                               ("product", ean13("4000000000006"),
                                [{"format": "EAN-13", "text": "4000000000006"}])):
        photo = tmp_path / (name + ".png")
        image.save(photo)

        def no_fetch(url):
            raise AssertionError("a photo without an ISBN must not ask a catalogue")

        summary = barcode_photo(photo, tmp_path / "work", location="Box 4", fetch=no_fetch, run_yaz=no_fetch)
        directory = tmp_path / "work" / name
        decoded = json.loads((directory / "barcode.json").read_text())
        (record,) = json.loads((directory / "records.json").read_text())
        assert decoded == {"file": photo.name, "codes": codes, "isbn": None}
        assert (record["read_status"], record["isbn"], record["title"], record["location"]) == (
            "no_barcode", "", "", "Box 4")
        assert record["photo"] == photo.name and record["needs_review"] is True
        assert "type the number in" in record["notes"].lower()
        assert (directory / "records.csv").read_bytes().startswith(b'\xef\xbb\xbf')
        assert (summary["photo"], summary["unreadable"], summary["directory"]) == (photo.name, 1, str(directory))


def test_a_japanese_isbn_uses_the_first_matching_catalogue_record_without_a_model(tmp_path):
    from home_library.pipeline import barcode_photo
    from home_library.records import COLUMNS

    photo = tmp_path / "barcode.jpg"
    ean13("9784000000000").save(photo)
    asked = []

    def fetch(url):
        asked.append(url)
        if "openbd" in url:
            return b'[{"summary": {"isbn": "9784000000000", "title": "Later Balloon"}}]'
        return b'''<rss xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcndl="http://ndl.go.jp/dcndl/terms/"
                       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><channel>
          <item><dc:title>Wrong Balloon</dc:title><dc:identifier xsi:type="dcndl:ISBN">9784000000017</dc:identifier></item>
          <item><dc:title>Amber Balloon</dc:title><dc:creator>Ada Reed</dc:creator><dc:publisher>Cloud Press</dc:publisher>
            <dc:date>2026</dc:date><dcndl:titleTranscription>AMBER BALLOON</dcndl:titleTranscription>
            <dcndl:seriesTitle>Invented Skies</dcndl:seriesTitle>
            <dc:identifier xsi:type="dcndl:ISBN">978-4-0000-0000-0</dc:identifier>
            <dc:identifier xsi:type="dcndl:NDLBibID">invented-2</dc:identifier></item>
          <item><dc:title>Second Balloon</dc:title><dc:identifier xsi:type="dcndl:ISBN">9784000000000</dc:identifier></item>
        </channel></rss>'''

    def no_yaz(commands):
        raise AssertionError("a Japanese ISBN must not use the Czech catalogue")

    summary = barcode_photo(photo, tmp_path / "work", location="Shelf 3", fetch=fetch, run_yaz=no_yaz)
    directory = tmp_path / "work" / "barcode"
    (record,) = json.loads((directory / "records.json").read_text())
    assert list(record) == COLUMNS
    assert (record["read_status"], record["isbn"], record["title"], record["language"]) == (
        "barcode", "9784000000000", "", "ja")
    assert (record["catalogue_title"], record["author"], record["publisher"], record["year"]) == (
        "Amber Balloon", "Ada Reed", "Cloud Press", "2026")
    assert (record["source"], record["source_id"], record["sort_key"], record["series"]) == (
        "ndl", "invented-2", "AMBER BALLOON", "Invented Skies")
    assert (record["candidate_count"], record["pick_verdict"], record["location"]) == (4, "match", "Shelf 3")
    assert summary["review"] == 1 and summary["seconds"] == {}
    assert len(asked) == 2 and all("isbn=9784000000000" in url for url in asked)

    asked.clear()
    barcode_photo(photo, tmp_path / "work", fetch=fetch, run_yaz=no_yaz)
    assert asked == []  # ISBN catalogue answers are cached as in the shelf pipeline


def test_an_isbn_without_a_matching_candidate_is_kept_with_a_note(tmp_path):
    from home_library.pipeline import barcode_photo

    photo = tmp_path / "barcode.png"
    ean13("9784000000000").save(photo)

    def fetch(url):
        return b'<rss><channel/></rss>' if "ndlsearch" in url else b'[{"summary": {"isbn": "9784000000017", "title": "Wrong Balloon"}}]'

    barcode_photo(photo, tmp_path / "work", fetch=fetch)
    (record,) = json.loads((tmp_path / "work/barcode/records.json").read_text())
    assert (record["read_status"], record["isbn"], record["catalogue_title"], record["author"]) == (
        "barcode", "9784000000000", "", "")
    assert "no catalogue match" in record["notes"].lower()


@pytest.mark.parametrize("isbn, language, sources", [
    ("9784000000000", "ja", ["ndl", "openbd"]),
    ("9788000000008", "cs", ["nkcr"]),
    ("9780000000002", "en", ["openlibrary", "loc"]),
    ("9781000000009", "en", ["openlibrary", "loc"]),
    ("9798000000007", "en", ["openlibrary", "loc"]),
])
def test_the_registration_group_selects_only_its_language_sources(tmp_path, isbn, language, sources):
    from home_library.pipeline import barcode_photo

    photo = tmp_path / "barcode.png"
    ean13(isbn).save(photo)
    asked = []

    def fetch(url):
        if "ndlsearch" in url:
            asked.append("ndl")
            return b'<rss><channel/></rss>'
        if "openbd" in url:
            asked.append("openbd")
            return b'[null]'
        if "openlibrary" in url:
            asked.append("openlibrary")
            return b'{}'
        asked.append("loc")
        return b'<searchRetrieveResponse xmlns="http://www.loc.gov/zing/srw/"/>'

    def yaz(commands):
        asked.append("nkcr")
        return 'Search was a success.\nNumber of hits: 0\n'

    barcode_photo(photo, tmp_path / "work", fetch=fetch, run_yaz=yaz)
    (record,) = json.loads((tmp_path / "work/barcode/records.json").read_text())
    assert (record["language"], record["isbn"], record["read_status"]) == (language, isbn, "barcode")
    assert asked == sources


@pytest.mark.parametrize("stop_at", ["ja", "cs", "en", None])
def test_an_unknown_group_tries_japanese_czech_then_english_until_records_are_returned(tmp_path, stop_at):
    from home_library.pipeline import barcode_photo

    photo = tmp_path / "barcode.png"
    ean13("9782000000006").save(photo)
    asked = []

    def fetch(url):
        if "ndlsearch" in url:
            asked.append("ndl")
            return b'<rss><channel/></rss>'
        if "openbd" in url:
            asked.append("openbd")
            return b'[{"summary": {"isbn": "9782000000006", "title": "Amber Balloon"}}]' if stop_at == "ja" else b'[null]'
        if "openlibrary" in url:
            asked.append("openlibrary")
            return b'{"ISBN:9782000000006": {"key": "/books/invented", "title": "Amber Balloon"}}' if stop_at == "en" else b'{}'
        asked.append("loc")
        return b'<searchRetrieveResponse xmlns="http://www.loc.gov/zing/srw/"/>'

    def yaz(commands):
        asked.append("nkcr")
        return 'Search was a success.\nNumber of hits: 1\nRecord type: USmarc\n001 invented\n020    $a 9782000000006\n245    $a Amber Balloon\n' if stop_at == "cs" else 'Search was a success.\nNumber of hits: 0\n'

    barcode_photo(photo, tmp_path / "work", fetch=fetch, run_yaz=yaz)
    (record,) = json.loads((tmp_path / "work/barcode/records.json").read_text())
    expected = ["ndl", "openbd"] + ([] if stop_at == "ja" else ["nkcr"])
    if stop_at not in ("ja", "cs"):
        expected += ["openlibrary", "loc"]
    assert asked == expected
    assert record["language"] == (stop_at or "unknown")
    assert record["catalogue_title"] == ("Amber Balloon" if stop_at else "")
    assert record["isbn"] == "9782000000006" and record["title"] == ""


def test_catalogue_failures_remain_visible_in_the_barcode_row(tmp_path):
    from home_library.lookup.errors import Unavailable
    from home_library.pipeline import barcode_photo

    photo = tmp_path / "barcode.png"
    ean13("9780000000002").save(photo)

    def fetch(url):
        raise Unavailable("invented offline catalogue")

    barcode_photo(photo, tmp_path / "work", fetch=fetch)
    (record,) = json.loads((tmp_path / "work/barcode/records.json").read_text())
    assert "No catalogue match" in record["notes"]
    assert "openlibrary unavailable" in record["notes"] and "loc unavailable" in record["notes"]
    assert record["isbn"] == "9780000000002" and record["read_status"] == "barcode"
