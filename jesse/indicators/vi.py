from collections import namedtuple

import numpy as np
import jesse_rust
from jesse.helpers import slice_candles

VI = namedtuple('VI', ['plus', 'minus'])


def vi(candles: np.ndarray, period: int = 14, sequential: bool = False) -> VI:
    """
    Vortex Indicator (VI)

    :param candles: np.ndarray
    :param period: int - default: 14
    :param sequential: bool - default: False

    :return: VI(plus, minus)
    """
    candles = slice_candles(candles, sequential)
    
    # Use the Rust implementation
    vi_plus, vi_minus = jesse_rust.vi(candles, period, sequential)
    
    if sequential:
        return VI(vi_plus, vi_minus)
    else:
        return VI(vi_plus[-1], vi_minus[-1])
