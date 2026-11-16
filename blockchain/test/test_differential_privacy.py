import pytest
from bitarray import bitarray

from src.differential_privacy import LocalDifferentialPrivacy


def test_flip_probability_matches_configured_epsilon():
    assert LocalDifferentialPrivacy.calculate_flip_probability(1.0) == pytest.approx(
        0.3775406688
    )
    assert LocalDifferentialPrivacy.calculate_flip_probability(None) == 0.0


def test_seeded_randomized_response_is_reproducible():
    original = bitarray("10101010")

    first = LocalDifferentialPrivacy.apply_randomized_response(
        original, epsilon=1.0, seed=42
    )
    second = LocalDifferentialPrivacy.apply_randomized_response(
        original, epsilon=1.0, seed=42
    )

    assert first == second
    assert len(first) == len(original)


def test_non_positive_epsilon_returns_a_copy():
    original = bitarray("10101010")

    result = LocalDifferentialPrivacy.apply_randomized_response(
        original, epsilon=0.0
    )

    assert result == original
    assert result is not original