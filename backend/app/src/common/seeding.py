"""Independent, reproducible random streams for experiment steps."""

from hashlib import sha256

from numpy.random import Generator, SeedSequence, default_rng


def make_rng(seed: int, purpose: str) -> Generator:
    """Return a NumPy random generator derived from the seed and purpose."""
    purpose_entropy = int.from_bytes(sha256(purpose.encode("utf-8")).digest(), "big")
    return default_rng(SeedSequence([seed, purpose_entropy]))
