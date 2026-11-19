def qgrams(s: str, q: int = 2, pad: bool = False) -> list:
    if pad:
        s = "_" * (q - 1) + s + "_" * (q - 1)
    if len(s) == 0:
        return []
    if len(s) < q:
        return [s]
    return [s[i:i + q] for i in range(len(s) - q + 1)]


def qgram_set(s: str, q: int = 2, pad: bool = False) -> set:
    return set(qgrams(s, q, pad))
