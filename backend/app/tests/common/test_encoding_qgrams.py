import pytest

from src.common.encoding.qgrams import extract_qgrams


def test_padded_and_unpadded_bigrams():
    assert extract_qgrams("abc", 2, "_") == {"_a", "ab", "bc", "c_"}
    assert extract_qgrams("abc", 2, "_", padding=False) == {"ab", "bc"}


def test_trigrams_add_two_characters_at_each_boundary():
    assert extract_qgrams("abc", 3, "^") == {"^^a", "^ab", "abc", "bc^", "c^^"}


def test_repeated_windows_collapse_and_short_unpadded_text_has_no_qgrams():
    assert extract_qgrams("aaaa", 2, "_", padding=False) == {"aa"}
    assert extract_qgrams("a", 3, "_", padding=False) == set()
    assert extract_qgrams("a", 3, "_") == {"__a", "_a_", "a__"}


@pytest.mark.parametrize("pad_char", ["a", "1", "漢", "", "__"])
def test_invalid_pad_char_is_rejected(pad_char):
    with pytest.raises(ValueError, match="pad_char"):
        extract_qgrams("abc", 2, pad_char)
