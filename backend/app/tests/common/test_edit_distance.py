from src.common.preprocessing.edit_distance import levenshtein


def test_edit_distance_handles_unicode_and_empty_fields():
    assert levenshtein("", "") == 0
    assert levenshtein("dose", "") == levenshtein("", "dose") == 4
    assert levenshtein("café", "cafe") == 1
