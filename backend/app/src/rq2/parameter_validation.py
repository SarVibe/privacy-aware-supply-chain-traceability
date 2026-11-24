import math
from collections.abc import Mapping

import numpy as np

from src.common.config import unit_interval


def validate_eps(eps):
    if isinstance(eps, (bool, np.bool_)):
        raise ValueError("eps must be a positive number or positive infinity")
    try:
        value = float(eps)
    except (TypeError, ValueError):
        raise ValueError("eps must be a positive number or positive infinity") from None
    if math.isnan(value):
        raise ValueError("eps must not be NaN")
    if value < 0:
        raise ValueError("eps must not be negative")
    if value != math.inf and value <= 0:
        raise ValueError("eps must be positive")
    return value


def validate_noise(rate):
    return unit_interval(rate, "noise rate")


def validate_overlap(overlap):
    try:
        value = float(overlap)
    except (TypeError, ValueError):
        raise ValueError("overlap must be within (0, 1]") from None
    if math.isnan(value) or value <= 0 or value > 1:
        raise ValueError("overlap must be within (0, 1]")
    return value


def validate_n_records(n_records):
    if isinstance(n_records, bool) or not isinstance(n_records, (int, np.integer)):
        raise ValueError("n_records must be a positive integer")
    if n_records <= 0:
        raise ValueError("n_records must be greater than zero")
    return int(n_records)


def validate_bit_top(bit_top):
    if isinstance(bit_top, bool) or not isinstance(bit_top, (int, np.integer)):
        raise ValueError("bit_top must be a positive integer")
    if bit_top <= 0:
        raise ValueError("bit_top must be greater than zero")
    return int(bit_top)


def validate_dataset(ds):
    n = getattr(ds, "n", None)
    if n is None or n < 4:
        raise ValueError("dataset must contain at least four records")
    raw = getattr(ds, "raw", None)
    norm = getattr(ds, "norm", None)
    if raw is None or norm is None or len(raw) == 0 or len(norm) == 0:
        raise ValueError("dataset must not be empty")


def validate_dictionary(dictionary):
    if not isinstance(dictionary, Mapping) or len(dictionary) == 0:
        raise ValueError("dictionary must not be empty")
