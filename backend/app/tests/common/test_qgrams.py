from src.common.preprocessor import TextPreprocessor
from src.common.qgram_extractor import QGramExtractor


def test_composite_qgrams_ignore_none_attributes():
    qgrams = QGramExtractor().extract_composite_qgrams(
        name="product", dosage=None, dosage_form=None, pack_size=None
    )

    assert not any("None" in qgram for qgram in qgrams)
    assert any(qgram.startswith("DOSE_W0_NA") for qgram in qgrams)


def test_common_qgram_extraction_uses_token_boundaries():
    qgrams = QGramExtractor(q=3).extract_token_qgrams("product 150mg")

    assert "__p" in qgrams
    assert "__1" in qgrams
    assert "t 1" not in qgrams


def test_common_preprocessor_normalizes_delimiters():
    assert TextPreprocessor.normalize("#102198**Didanosine 200mg [Videx], tablets") == (
        "didanosine 200mg videx tablets"
    )
