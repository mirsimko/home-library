from home_library.merge import match_key


def test_match_key_ignores_width_case_spaces_and_punctuation():
    assert match_key("ＴＨＥ  Blue-Kite!") == "thebluekite"
    assert match_key("The Blue Kite") == "thebluekite"


def test_match_key_keeps_diacritics_kana_and_digits_significant():
    assert match_key("Zeleny drak") != match_key("Zelený drak")
    assert match_key("Zelený drak") == "zelenýdrak"
    assert match_key("あかいふうせん") != match_key("アカイフウセン")
    assert match_key("ハリー・ポッター 1") != match_key("ハリー・ポッター 2")
    assert match_key("ハリー・ポッター 1") == "ハリーポッター1"


def test_match_key_of_punctuation_only_is_empty():
    assert match_key(" ・!? ") == ""


def test_match_key_folds_half_width_katakana_to_full_width():
    assert match_key("ｱｶｲ") == "アカイ"
