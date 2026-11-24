import numpy as np
from src.common.encoding.bloom_filter import BloomFilterEncoder
from src.common.encoding.versioned_bloom import BloomNamespace, VersionedBloom


def test_encode_and_byte_round_trip_preserves_bits():
    encoder = BloomFilterEncoder(64, 3, 2, b"test-key", "_")
    bits = encoder.encode("some product")
    namespace = BloomNamespace("fixture", "fixture-key")
    encoded = VersionedBloom(bits, namespace)
    restored = VersionedBloom.unpack(encoded.packed_bytes(), 64, namespace)
    np.testing.assert_array_equal(restored.bits, bits)
    assert restored.namespace == namespace


def test_empty_text_creates_an_empty_filter():
    encoder = BloomFilterEncoder(32, 2, 2, b"test-key", "_")
    assert not encoder.encode("").any()
