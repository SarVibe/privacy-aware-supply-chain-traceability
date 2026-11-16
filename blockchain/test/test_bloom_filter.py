from bitarray import bitarray

from src.keyed_bloom_filter import KeyedBloomFilter


def test_encode_and_byte_round_trip_preserves_bits():
    engine = KeyedBloomFilter(length=64, num_hashes=3, secret_key="test-key")
    encoded = engine.encode({"alpha", "beta"})

    restored = KeyedBloomFilter.from_bytes(
        KeyedBloomFilter.to_bytes(encoded),
        length=64,
    )

    assert len(encoded) == 64
    assert encoded == restored
    assert encoded.count(1) > 0


def test_empty_qgrams_create_an_empty_filter():
    engine = KeyedBloomFilter(length=32, num_hashes=2, secret_key=b"test-key")

    encoded = engine.encode(set())

    assert encoded == bitarray("0" * 32)