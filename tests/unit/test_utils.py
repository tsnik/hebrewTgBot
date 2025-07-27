from utils import normalize_hebrew, parse_translations


def test_normalize_hebrew():
    assert normalize_hebrew("שָׁלוֹם") == "שלום"
    assert normalize_hebrew("מַיִם") == "מים"
    assert normalize_hebrew("בַּיִת") == "בית"
    assert normalize_hebrew("כָּתַב") == "כתב"
    assert normalize_hebrew("") == ""
    assert normalize_hebrew("abc") == "abc"


def test_parse_translations():
    # Test case 1: Simple translation
    raw_text_1 = "hello, world"
    expected_1 = [
        {"translation_text": "hello", "context_comment": None, "is_primary": True},
        {"translation_text": "world", "context_comment": None, "is_primary": False},
    ]
    assert parse_translations(raw_text_1) == expected_1

    # Test case 2: Translation with context
    raw_text_2 = "go (by foot), walk"
    expected_2 = [
        {"translation_text": "go", "context_comment": "by foot", "is_primary": True},
        {"translation_text": "walk", "context_comment": "by foot", "is_primary": False},
    ]
    assert parse_translations(raw_text_2) == expected_2

    # Test case 3: Multiple contexts
    raw_text_3 = "run (quickly); flee"
    expected_3 = [
        {"translation_text": "run", "context_comment": "quickly", "is_primary": True},
        {"translation_text": "flee", "context_comment": None, "is_primary": False},
    ]
    assert parse_translations(raw_text_3) == expected_3

    # Test case 4: Empty string
    raw_text_4 = ""
    expected_4 = []
    assert parse_translations(raw_text_4) == expected_4

    # Test case 5: Only context
    raw_text_5 = "(alone)"
    expected_5 = []
    assert parse_translations(raw_text_5) == expected_5
