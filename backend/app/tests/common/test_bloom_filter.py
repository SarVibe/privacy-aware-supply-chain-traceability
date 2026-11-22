import hashlib
import hmac

import numpy as np
import pytest

from src.common.encoding.bloom_filter import BloomFilterEncoder
from src.common.encoding.qgrams import extract_qgrams


def test_hmac_positions_match_formula_and_are_deterministic():
    key = b"test-key"
    encoder = BloomFilterEncoder(1024, 4, 2, key, "_")
    expected_positions = {
        int.from_bytes(hmac.new(key, f"{i}:{gram}".encode(), hashlib.sha256).digest()[:4], "big") % 1024
        for gram in {"_é", "éa", "a_"}
        for i in range(4)
    }
    bits = encoder.encode("éa")
    assert bits.dtype == np.uint8 and bits.shape == (1024,)
    assert set(np.flatnonzero(bits)) == expected_positions
    np.testing.assert_array_equal(bits, encoder.encode("éa"))
    assert not np.array_equal(bits, BloomFilterEncoder(1024, 4, 2, b"other-key", "_").encode("éa"))


def test_reuses_hmac_positions_for_shared_qgrams(monkeypatch):
    digest = hmac.digest
    calls = []

    def track(key, message, algorithm):
        calls.append(message)
        return digest(key, message, algorithm)

    monkeypatch.setattr(hmac, "digest", track)
    encoder = BloomFilterEncoder(1024, 4, 2, b"test-key", "_")
    encoder.encode("abc")
    encoder.encode("abd")
    encoder.encode("abc")
    assert len(calls) == 4 * 6
    assert len(set(calls)) == len(calls)


def test_rejects_non_power_of_two():
    with pytest.raises(ValueError, match="power of two"):
        BloomFilterEncoder(1000, 4, 2, b"test-key", "_")


@pytest.mark.parametrize("k", [4, 30])
def test_bit_count_is_bounded_at_any_k(k):
    text = "banana"
    bits = BloomFilterEncoder(1024, k, 2, b"test-key", "_").encode(text)
    assert 0 < np.count_nonzero(bits) <= k * len(extract_qgrams(text, 2, "_"))


def test_encode_many_matches_single_encodes_and_handles_empty_inputs():
    encoder = BloomFilterEncoder(1024, 4, 3, b"test-key", "_")
    texts = ["aaa", "ababa", "", "aaa"]
    expected = np.stack([encoder.encode(text) for text in texts])
    np.testing.assert_array_equal(encoder.encode_many(iter(texts)), expected)
    assert encoder.encode_many([]).shape == (0, 1024)
    assert not expected[2].any()


def test_hook_receives_finished_bits_and_runs_for_each_record():
    options = (128, 4, 2, b"test-key", "_")
    expected = BloomFilterEncoder(*options).encode_many(["abc", "abc", ""])
    np.testing.assert_array_equal(
        BloomFilterEncoder(*options, post_transform=None).encode_many(["abc", "abc", ""]), expected
    )
    received = []

    def complement(bits):
        received.append(bits.copy())
        return bits ^ np.uint8(1)

    actual = BloomFilterEncoder(*options, post_transform=complement).encode_many(["abc", "abc", ""])
    np.testing.assert_array_equal(np.stack(received), expected)
    np.testing.assert_array_equal(actual, expected ^ np.uint8(1))


def test_hook_validates_output_contract():
    encoder = BloomFilterEncoder(128, 4, 2, b"test-key", "_", post_transform=lambda bits: bits[:-1])
    with pytest.raises(ValueError, match="post_transform"):
        encoder.encode("abc")
