import numpy as np

from src.common.seeding import make_rng


def test_identical_seed_and_purpose_replay_the_same_draws():
    first = make_rng(7, "split").integers(10_000, size=16)
    second = make_rng(7, "split").integers(10_000, size=16)
    np.testing.assert_array_equal(first, second)


def test_seed_and_purpose_both_change_the_stream():
    reference = make_rng(7, "split").integers(10_000, size=16)
    assert not np.array_equal(reference, make_rng(8, "split").integers(10_000, size=16))
    assert not np.array_equal(reference, make_rng(7, "entity_cap").integers(10_000, size=16))
