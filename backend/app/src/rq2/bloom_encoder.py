import hashlib
import hmac

import numpy as np

from src.rq2.qgram_utils import qgram_set


def _is_pow2(n: int) -> bool:
    return n > 0 and (n & (n - 1)) == 0


class BloomEncoder:
    def __init__(self, l: int, k: int, key: bytes, q: int = 2, pad: bool = False):
        if l < 2 or k < 1:
            raise ValueError("need l >= 2 and k >= 1")
        if k > l:
            raise ValueError("k must be <= l")
        self.l, self.k, self.key, self.q, self.pad = l, k, key, q, pad
        self._base = {}

    def _hashes(self, gram: str):
        h = self._base.get(gram)
        if h is None:
            digest = hmac.new(self.key, gram.encode("utf-8"), hashlib.sha256).digest()
            h = (int.from_bytes(digest[:8], "big"), int.from_bytes(digest[8:16], "big"))
            self._base[gram] = h
        return h

    def gram_positions(self, grams) -> np.ndarray:
        grams = list(grams)
        if not grams:
            return np.zeros((0, self.k), dtype=np.int64)
        h = np.array([self._hashes(g) for g in grams], dtype=np.uint64)
        h1 = (h[:, 0] % np.uint64(self.l)).astype(np.int64)
        step = (h[:, 1] % np.uint64(self.l - 1)).astype(np.int64) + 1
        if _is_pow2(self.l):
            step = step | 1
        else:
            gcd = np.gcd(step, self.l)
            while np.any(gcd != 1):
                bad = gcd != 1
                step[bad] = step[bad] % (self.l - 1) + 1
                gcd = np.gcd(step, self.l)
        i = np.arange(self.k, dtype=np.int64)
        return (h1[:, None] + i[None, :] * step[:, None]) % self.l

    def encode_many(self, strings) -> np.ndarray:
        index, inv, uniq = {}, np.empty(len(strings), dtype=np.int64), []
        for i, s in enumerate(strings):
            j = index.get(s)
            if j is None:
                j = len(uniq)
                index[s] = j
                uniq.append(s)
            inv[i] = j
        gram_sets = [qgram_set(s, self.q, self.pad) for s in uniq]
        vocab = {}
        for gs in gram_sets:
            for g in gs:
                if g not in vocab:
                    vocab[g] = len(vocab)
        pos = self.gram_positions(list(vocab))
        out = np.zeros((len(uniq), self.l), dtype=np.uint8)
        for r, gs in enumerate(gram_sets):
            if gs:
                idx = [vocab[g] for g in gs]
                out[r, pos[idx].ravel()] = 1
        return out[inv]

    def encode(self, s: str) -> np.ndarray:
        return self.encode_many([s])[0]
