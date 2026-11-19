import random
from dataclasses import dataclass

import numpy as np


ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"


@dataclass(frozen=True)
class NoiseSpec:
    rate: float
    min_len: int = 3
    min_edits: int = 1

    def __post_init__(self):
        if not 0.0 <= self.rate <= 1.0:
            raise ValueError("noise rate must be in [0, 1]")
        if self.min_len < 0:
            raise ValueError("min_len must be non-negative")
        if self.min_edits < 1:
            raise ValueError("min_edits must be >= 1")


def mutate_once(s: str, rng: np.random.Generator) -> str:
    if not s:
        return s
    op = int(rng.integers(4))
    n = len(s)
    if op == 0:
        i = int(rng.integers(n))
        return s[:i] + ALPHABET[int(rng.integers(len(ALPHABET)))] + s[i + 1:]
    if op == 1 and n > 1:
        i = int(rng.integers(n))
        return s[:i] + s[i + 1:]
    if op == 2:
        i = int(rng.integers(n + 1))
        return s[:i] + ALPHABET[int(rng.integers(len(ALPHABET)))] + s[i:]
    if op == 3 and n > 1:
        i = int(rng.integers(n - 1))
        return s[:i] + s[i + 1] + s[i] + s[i + 2:]
    i = int(rng.integers(n))
    return s[:i] + ALPHABET[int(rng.integers(len(ALPHABET)))] + s[i + 1:]


def add_typos(s: str, rate: float, rng: np.random.Generator, spec: NoiseSpec | None = None) -> str:
    if not 0.0 <= rate <= 1.0:
        raise ValueError("noise rate must be in [0, 1]")
    spec = spec or NoiseSpec(rate=rate)
    if len(s) <= spec.min_len or rate <= 0:
        return s
    for _ in range(max(spec.min_edits, int(len(s) * rate))):
        s = mutate_once(s, rng)
    return s


def add_noise(strings, rate: float, rng: np.random.Generator, spec: NoiseSpec | None = None) -> list:
    return [add_typos(s, rate, rng, spec) for s in strings]


def levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def inject_typo(text: str, noise_rate: float, rng: random.Random) -> str:
    """Python-random-compatible typo injection used by RQ1 generation."""
    if noise_rate <= 0.0 or not text:
        return text
    chars = list(text)
    num_mutations = max(1, int(len(chars) * noise_rate))
    for _ in range(num_mutations):
        if len(chars) <= 3:
            break
        mutation = rng.choice(["substitute", "delete", "insert", "transpose"])
        idx = rng.randint(0, len(chars) - 1)
        if mutation == "substitute":
            chars[idx] = rng.choice(ALPHABET)
        elif mutation == "delete" and len(chars) > 3:
            chars.pop(idx)
        elif mutation == "insert":
            chars.insert(idx, rng.choice(ALPHABET))
        elif mutation == "transpose" and idx < len(chars) - 1:
            chars[idx], chars[idx + 1] = chars[idx + 1], chars[idx]
    return "".join(chars)
