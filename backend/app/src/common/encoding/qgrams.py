"""Extract character q-gram sets from whole strings."""


def validate_qgram_parameters(q: int, pad_char: str) -> None:
    """Validate q and the character used for boundary padding."""
    if type(q) is not int or q < 1:
        raise ValueError("q must be an integer >= 1")
    if not isinstance(pad_char, str) or len(pad_char) != 1 or pad_char.isalnum():
        raise ValueError("pad_char must be one non-alphanumeric character")


def extract_qgrams(text: str, q: int, pad_char: str, padding: bool = True) -> set[str]:
    """Return distinct character windows, optionally padded at both ends."""
    validate_qgram_parameters(q, pad_char)
    if padding:
        boundary = pad_char * (q - 1)
        text = boundary + text + boundary
    return {text[i:i + q] for i in range(len(text) - q + 1)}
