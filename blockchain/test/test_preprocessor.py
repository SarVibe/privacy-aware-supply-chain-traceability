from src.common.preprocessor import TextPreprocessor


def test_normalize_removes_inventory_markers_and_punctuation():
    normalized = TextPreprocessor.normalize(
        "#102198**Didanosine 200mg [Videx], tablets"
    )

    assert normalized == "didanosine 200mg videx tablets"


def test_composite_qgrams_keep_dosage_and_form_signatures():
    qgrams = TextPreprocessor.extract_composite_qgrams(
        "Didanosine 200mg tablets",
        dosage="200mg",
        dosage_form="Tablets",
        pack_size="30",
    )

    assert "EXACT_DOSE_W0_200mg" in qgrams
    assert "EXACT_FORM_tablets" in qgrams
    assert "PACK_30" in qgrams