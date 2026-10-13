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
