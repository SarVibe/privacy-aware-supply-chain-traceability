"""Step 1 of the C1 pipeline: standardize raw text for RQ2."""
import re
import unicodedata


_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize(text) -> str:
    """Collapse text variants to a lowercase alphanumeric representation."""
    if text is None:
        return ""
    t = unicodedata.normalize("NFKD", str(text)).lower()
    return _NON_ALNUM.sub("", t)
