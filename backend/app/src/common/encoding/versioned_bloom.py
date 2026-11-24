"""Versioned filter values and their stable ledger wire format."""

import hmac
import os
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from src.common.config import BloomConfig, composite_encoder_version
from src.common.encoding.bloom_filter import BloomFilterEncoder
from src.common.preprocessing.field_builder import composite_field_string


class IncompatibleBloomError(ValueError):
    """The available vector cannot be compared in this encoder and key namespace."""


@dataclass(frozen=True)
class BloomNamespace:
    encoder_version: str
    key_id: str

    def qualify(self, cluster_id: str) -> str:
        if not cluster_id or "/" in cluster_id:
            raise ValueError("Expected a non-empty local cluster ID without slashes")
        return f"{self.encoder_version}/{self.key_id}/{cluster_id}"

    def local_id(self, persisted_id: str) -> str:
        prefix = f"{self.encoder_version}/{self.key_id}/"
        if not persisted_id.startswith(prefix):
            raise IncompatibleBloomError("Unversioned or incompatible ledger filters. Re-encode into an empty ledger.")
        cluster_id = persisted_id.removeprefix(prefix)
        if not cluster_id or "/" in cluster_id:
            raise IncompatibleBloomError("Invalid versioned cluster identifier on the ledger.")
        return cluster_id


@dataclass(frozen=True, eq=False)
class VersionedBloom:
    bits: NDArray[np.uint8]
    namespace: BloomNamespace

    def __post_init__(self):
        if self.bits.ndim != 1 or self.bits.dtype != np.uint8 or not self.bits.size or np.any(self.bits > 1):
            raise ValueError("Expected a non-empty uint8 vector of binary bits")
        object.__setattr__(self, "bits", np.frombuffer(self.bits.tobytes(), dtype=np.uint8))

    def copy(self):
        return self

    def require_namespace(self, expected: BloomNamespace) -> None:
        if self.namespace != expected:
            raise IncompatibleBloomError("Bloom encoder version or key namespace mismatch")

    def packed_bytes(self) -> bytes:
        return np.packbits(self.bits, bitorder="big").tobytes()

    @classmethod
    def unpack(cls, payload: bytes, length: int, namespace: BloomNamespace):
        if len(payload) != (length + 7) // 8:
            raise IncompatibleBloomError("Persisted Bloom vector length mismatch")
        return cls(np.unpackbits(np.frombuffer(payload, dtype=np.uint8), count=length, bitorder="big"), namespace)


def environment_bloom_key() -> bytes:
    value = os.environ.get("SHARED_SECRET_KEY")
    if value is None or not value.strip():
        raise RuntimeError("SHARED_SECRET_KEY is required to serve Bloom encoding")
    return value.encode("utf-8")


class CompositeBloomEncoder:
    """Adapt the canonical encoder to individual records and versioned vector values."""

    def __init__(self, settings: BloomConfig, key: bytes):
        l, k, q, pad = settings.l, settings.k, settings.q, settings.pad_char
        self.namespace = BloomNamespace(
            composite_encoder_version(l, k, q, pad),
            hmac.digest(key, b"c1-serving-bloom-key-namespace-v1", "sha256").hex(),
        )
        self._encoder = BloomFilterEncoder(l, k, q, key, pad)

    def encode_record(self, description, dosage=None, dosage_form=None, pack_size=None) -> VersionedBloom:
        text = composite_field_string(description, dosage, dosage_form, pack_size)
        return VersionedBloom(self._encoder.encode(text), self.namespace)
