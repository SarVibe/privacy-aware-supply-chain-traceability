"""
src/keyed_bloom_filter.py
Component 1: Pre-Ledger Cross-Organizational Data Harmonization

Role:
- Encodes tokenized q-grams into a fixed-length Bit Array (Keyed Bloom Filter).
- Employs HMAC-SHA256 with a shared secret key (kappa) to prevent dictionary / frequency attacks.
- Supports dynamic parameter tuning (l in [256..1024], k in [4..30]) for RQ2 Collision Experiments.
- Provides serialization helpers (to_bytes, from_bytes, to_hex) for Blockchain payload commitment.
"""

import os
import hmac
import hashlib
from pathlib import Path
from typing import Optional, Set, Union
from bitarray import bitarray
from dotenv import load_dotenv

# Search current directory, parent directory, and venv for .env
for p in [Path.cwd(), Path(__file__).resolve().parent.parent, Path(__file__).resolve().parent.parent.parent]:
    env_file = p / ".env"
    if env_file.exists():
        load_dotenv(dotenv_path=env_file)
        break


class KeyedBloomFilter:
    """
    Cryptographic Keyed Bloom Filter Engine implementing:
    B_{p_i} <- GenerateBloomFilter(r_{p_i}, A, l, k, kappa)
    """

    DEFAULT_LENGTH = int(os.getenv("DEFAULT_BF_LENGTH", 1024))
    DEFAULT_NUM_HASHES = int(os.getenv("DEFAULT_NUM_HASHES", 4))

    def __init__(
        self,
        length: Optional[int] = None,
        num_hashes: Optional[int] = None,
        secret_key: Union[str, bytes, None] = None
    ):
        """
        Parameters:
        - length (l): Length of the bit array (default: from .env DEFAULT_BF_LENGTH or 1024).
        - num_hashes (k): Number of independent hash functions (default: from .env DEFAULT_NUM_HASHES or 4).
        - secret_key (kappa): Shared secret key across supply chain consortium (default: from .env SHARED_SECRET_KEY).
        """
        self.length = length if length is not None else self.DEFAULT_LENGTH
        self.num_hashes = num_hashes if num_hashes is not None else self.DEFAULT_NUM_HASHES

        # Resolve secret key from parameter, environment, or secure fallback
        if secret_key is None:
            resolved_key = os.getenv("SHARED_SECRET_KEY", "c1_consortium_shared_secret_salt_2026")
        else:
            resolved_key = secret_key

        if isinstance(resolved_key, str):
            self.secret_key = resolved_key.encode("utf-8")
        else:
            self.secret_key = resolved_key

    def _hash_position(self, qgram: str, hash_index: int) -> int:
        """
        Computes a cryptographic bit position for a q-gram using HMAC-SHA256.
        Salted with hash_index to simulate k independent hash functions.
        """
        message = f"{qgram}:{hash_index}".encode("utf-8")
        digest = hmac.new(self.secret_key, message, hashlib.sha256).digest()

        # Extract 64-bit unsigned integer from digest prefix
        raw_int = int.from_bytes(digest[:8], byteorder="big", signed=False)
        return raw_int % self.length

    def encode(self, qgrams: Set[str]) -> bitarray:
        bf = bitarray(self.length, endian="big")
        bf.setall(0)

        if not qgrams:
            return bf

        for qgram in qgrams:
            for i in range(self.num_hashes):
                pos = self._hash_position(qgram, i)
                bf[pos] = 1

        return bf

    @staticmethod
    def calculate_bit_density(bf: bitarray) -> float:
        """
        Measures the empirical bit saturation (proportion of 1-bits):
        Bit Density = |bf| / l
        Essential metric for RQ2 (Collision Rate vs Probable Privacy).
        """
        if len(bf) == 0:
            return 0.0
        return bf.count(1) / float(len(bf))

    @staticmethod
    def to_bytes(bf: bitarray) -> bytes:
        """Converts bitarray to raw bytes for on-chain storage."""
        return bf.tobytes()

    @staticmethod
    def to_hex(bf: bitarray) -> str:
        """Converts bitarray to hex string (e.g., '0x...') for EVM smart contracts."""
        return "0x" + bf.tobytes().hex()

    @classmethod
    def from_bytes(cls, raw_bytes: bytes, length: Optional[int] = None) -> bitarray:
        """Restores bitarray from raw bytes retrieved from blockchain view call."""
        len_val = length if length is not None else cls.DEFAULT_LENGTH
        bf = bitarray(endian="big")
        bf.frombytes(raw_bytes)
        return bf[:len_val]

    @classmethod
    def from_hex(cls, hex_str: str, length: Optional[int] = None) -> bitarray:
        """Restores bitarray from EVM hex string."""
        clean_hex = hex_str[2:] if hex_str.startswith("0x") else hex_str
        if len(clean_hex) % 2 != 0:
            clean_hex = "0" + clean_hex
        raw_bytes = bytes.fromhex(clean_hex)
        return cls.from_bytes(raw_bytes, length)


if __name__ == "__main__":
    from src.common.preprocessor import TextPreprocessor

    test_desc = "Didanosine 200mg [Videx], tablets"
    cleaned = TextPreprocessor.normalize(test_desc)
    qgrams = TextPreprocessor.extract_token_qgrams(cleaned, q=3)

    bf_engine = KeyedBloomFilter()
    bf = bf_engine.encode(qgrams)

    density = KeyedBloomFilter.calculate_bit_density(bf)
    hex_repr = KeyedBloomFilter.to_hex(bf)

    print("--- Keyed Bloom Filter Test ---")
    print(f"Input:        '{test_desc}'")
    print(f"Total q-grams: {len(qgrams)}")
    print(f"Filter Length: {len(bf)} bits")
    print(f"Bits set to 1: {bf.count(1)}")
    print(f"Bit Density:   {density:.4f}")
    print(f"Hex Prefix:    {hex_repr[:34]}... ({len(hex_repr)} chars)")