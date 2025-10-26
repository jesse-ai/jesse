from collections import namedtuple

import numpy as np

from jesse.helpers import slice_candles

# Import the high-performance Rust implementation
from jesse_rust import dm as dm_rust  # type: ignore

DM = namedtuple('DM', ['plus', 'minus'])


def dm(candles: np.ndarray, period: int = 14, sequential: bool = False) -> DM:
    """
    DM - Directional Movement

    :param candles: np.ndarray
    :param period: int - default: 14
    :param sequential: bool - default: False

    :return: DM(plus, minus)
    """
    candles = slice_candles(candles, sequential)
    
    # Convert to float64 for Rust compatibility
    candles_f64 = np.asarray(candles, dtype=np.float64)
    
    # Call the Rust implementation
    plus, minus = dm_rust(candles_f64, period)
    
    if sequential:
        return DM(plus, minus)
    else:
        return DM(plus[-1], minus[-1])
