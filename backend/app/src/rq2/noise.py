"""Synthetic typo generator (same semantics as the C1 exp1 noise generator).

For a noise rate r every string receives max(1, int(len * r)) random character
edits (substitute / delete / insert / transpose). rate == 0 leaves it unchanged.
"""
import numpy as np

ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"


def mutate_once(s: str, rng: np.random.Generator) -> str:
    if not s:
        return s
    op = int(rng.integers(4))
    n = len(s)
    if op == 0:                                   # substitute
        i = int(rng.integers(n))
        return s[:i] + ALPHABET[int(rng.integers(len(ALPHABET)))] + s[i + 1:]
    if op == 1 and n > 1:                         # delete
        i = int(rng.integers(n))
        return s[:i] + s[i + 1:]
    if op == 2:                                   # insert
        i = int(rng.integers(n + 1))
        return s[:i] + ALPHABET[int(rng.integers(len(ALPHABET)))] + s[i:]
    if op == 3 and n > 1:                         # transpose adjacent chars
        i = int(rng.integers(n - 1))
        return s[:i] + s[i + 1] + s[i] + s[i + 2:]
    i = int(rng.integers(n))                      # fallback (n == 1): substitute
    return s[:i] + ALPHABET[int(rng.integers(len(ALPHABET)))] + s[i + 1:]


def add_typos(s: str, rate: float, rng: np.random.Generator) -> str:
    if rate <= 0:
        return s
    for _ in range(max(1, int(len(s) * rate))):
        s = mutate_once(s, rng)
    return s


def add_noise(strings, rate: float, rng: np.random.Generator) -> list:
    return [add_typos(s, rate, rng) for s in strings]
