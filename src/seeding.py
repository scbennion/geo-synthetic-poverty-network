"""One seed for every random draw in a run."""
import random

import numpy as np

DEFAULT_SEED = 42  # the r_seed the synthesis driver has always used


def add_seed_arg(parser):
    parser.add_argument('--seed', type=int, default=DEFAULT_SEED,
                        help=f'random seed for all stochastic steps (default {DEFAULT_SEED})')
    return parser


def seed_everything(seed):
    """Seed Python's `random` and return a NumPy Generator built from the same seed.

    Python `random` is still used by the household, education and tools modules;
    NumPy and pandas draws take the returned Generator explicitly.
    """
    random.seed(seed)
    return np.random.default_rng(seed)
