from collections import namedtuple

import numpy as np

from jesse.helpers import slice_candles

# Import the high-performance Rust implementation
from jesse_rust import stochf as stochf_rust  # type: ignore

StochasticFast = namedtuple('StochasticFast', ['k', 'd'])

def stochf(candles: np.ndarray, fastk_period: int = 5, fastd_period: int = 3, fastd_matype: int = 0,
           sequential: bool = False) -> StochasticFast:
    """
    Stochastic Fast

    :param candles: np.ndarray
    :param fastk_period: int - default: 5
    :param fastd_period: int - default: 3
    :param fastd_matype: int - default: 0
    :param sequential: bool - default: False

    :return: StochasticFast(k, d)
    """
    if fastd_matype == 24 or fastd_matype == 29:
        raise ValueError("VWMA (matype 24) and VWAP (matype 29) cannot be used in stochf indicator.")

    candles = slice_candles(candles, sequential)

    # Convert to float64 for Rust compatibility
    candles_f64 = np.asarray(candles, dtype=np.float64)
    
    # Call the Rust implementation
    k, d = stochf_rust(candles_f64, fastk_period, fastd_period, fastd_matype)
    
    if sequential:
        return StochasticFast(k, d)
    else:
        return StochasticFast(k[-1], d[-1])
