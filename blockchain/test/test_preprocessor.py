from src.common.preprocessing.field_builder import composite_field_string
from src.common.encoding.qgrams import extract_qgrams


def test_normalize_preserves_digits_and_removes_punctuation():
    assert composite_field_string("#102198**Didanosine 200mg [Videx], tablets", None, None, None) == (
        "102198didanosine200mgvidextablets|||"
    )


def test_whole_composite_has_dosage_and_form_boundaries():
    text = composite_field_string("Product A", "20mg", "Tablet", "10")
    assert text == "producta|20mg|tablet|10"
    grams = extract_qgrams(text, 2, "_")
    assert {"a|", "|2", "g|", "|t", "_p", "0_"} <= grams
