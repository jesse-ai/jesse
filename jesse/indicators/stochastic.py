from collections import namedtuple

import numpy as np

from jesse.helpers import slice_candles

# Import the high-performance Rust implementation
from jesse_rust import stoch as stoch_rust  # type: ignore

Stochastic = namedtuple('Stochastic', ['k', 'd'])


def stoch(candles: np.ndarray, fastk_period: int = 14, slowk_period: int = 3, slowk_matype: int = 0,
          slowd_period: int = 3, slowd_matype: int = 0, sequential: bool = False) -> Stochastic:
    """
    The Stochastic Oscillator

    :param candles: np.ndarray
    :param fastk_period: int - default: 14
    :param slowk_period: int - default: 3
    :param slowk_matype: int - default: 0
    :param slowd_period: int - default: 3
    :param slowd_matype: int - default: 0
    :param sequential: bool - default: False

    :return: Stochastic(k, d)
    """
    if any(matype in (24, 29) for matype in (slowk_matype, slowd_matype)):
        raise ValueError("VWMA (matype 24) and VWAP (matype 29) cannot be used in stochastic indicator.")

    candles = slice_candles(candles, sequential)

    # Convert to float64 for Rust compatibility
    candles_f64 = np.asarray(candles, dtype=np.float64)
    
    # Call the Rust implementation
    k, d = stoch_rust(candles_f64, fastk_period, slowk_period, slowk_matype, slowd_period, slowd_matype)
    
    if sequential:
        return Stochastic(k, d)
    else:
        return Stochastic(k[-1], d[-1])
