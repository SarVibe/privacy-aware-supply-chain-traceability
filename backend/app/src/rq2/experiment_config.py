"""Defaults shared by the RQ2 measurement functions."""

from src.common.config import load_config
from src.common.linking.threshold import threshold_values

RQ2_CONFIG = load_config("rq2")
DEFAULT_Q = RQ2_CONFIG.bloom.q
TAU_GRID = threshold_values(RQ2_CONFIG.tau_grid)
