"""Encode padded q-gram sets as keyed NumPy Bloom filters."""

import hmac
from collections.abc import Callable, Iterable

import numpy as np
from numpy.typing import NDArray

from src.common.encoding.qgrams import extract_qgrams, validate_qgram_parameters


class BloomFilterEncoder:
    """Use indexed HMAC-SHA256 positions and cache them per encoder."""

    def __init__(
        self,
        l: int,
        k: int,
        q: int,
        key: bytes,
        pad_char: str,
        post_transform: Callable[[NDArray[np.uint8]], NDArray[np.uint8]] | None = None,
    ) -> None:
        if type(l) is not int or l < 1 or l & (l - 1):
            raise ValueError("l must be a positive power of two")
        if type(k) is not int or k < 1:
            raise ValueError("k must be an integer >= 1")
        validate_qgram_parameters(q, pad_char)
        self._length = l
        self._k = k
        self._q = q
        self._key = key
        self._pad_char = pad_char
        self._post_transform = post_transform
        self._indices: dict[str, NDArray[np.intp]] = {}

    def _positions(self, qgram: str) -> NDArray[np.intp]:
        positions = self._indices.get(qgram)
        if positions is None:
            positions = np.fromiter(
                (
                    int.from_bytes(hmac.digest(self._key, f"{i}:{qgram}".encode("utf-8"), "sha256")[:4], "big")
                    % self._length
                    for i in range(self._k)
                ),
                dtype=np.intp,
                count=self._k,
            )
            self._indices[qgram] = positions
        return positions

    def encode(self, text: str) -> NDArray[np.uint8]:
        """Encode one string, then apply the optional per-record transform."""
        bits = np.zeros(self._length, dtype=np.uint8)
        if text:
            for qgram in extract_qgrams(text, self._q, self._pad_char):
                bits[self._positions(qgram)] = 1
        if self._post_transform is not None:
            bits = self._post_transform(bits)
            if not isinstance(bits, np.ndarray) or bits.shape != (self._length,) or bits.dtype != np.uint8:
                raise ValueError("post_transform must return a uint8 array of shape (l,)")
        return bits

    def encode_many(self, texts: Iterable[str]) -> NDArray[np.uint8]:
        """Encode one filter per input string, preserving input order."""
        texts = list(texts)
        bits = np.empty((len(texts), self._length), dtype=np.uint8)
        for index, text in enumerate(texts):
            bits[index] = self.encode(text)
        return bits
