"""Central experiment defaults (one place, so every script is consistent)."""
import numpy as np

DEFAULT_LS = (2048, 1024, 512, 256)          # Bloom filter lengths l
DEFAULT_KS = (2, 4, 8, 15, 30)               # number of hash functions k
DEFAULT_NOISES = (0.0, 0.05, 0.15, 0.30)     # typo rates (fraction of characters mutated)
DEFAULT_Q = 2                                # q-gram size
DEFAULT_PAD = False                          # no padding characters
STANDARD_CONFIG = (1024, 4)                  # "standard" Bloom filter baseline (l, k)

# Dice thresholds searched when tuning tau per configuration (validation split)
TAU_GRID = np.round(np.arange(0.30, 1.0001, 0.005), 4)

DEGENERATE_FILL = 0.95    # fill ratio above this => filter is saturated / unusable
REID_TOPK = (1, 5, 10)
REID_DELTA = 0.02         # "plausible candidate" = Dice within delta of best score
BIT_ATTACK_TOP_BITS = 100 # number of most-frequent bits attacked by the bit/q-gram attack
