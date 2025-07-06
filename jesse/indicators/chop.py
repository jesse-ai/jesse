from typing import Union

import numpy as np

from jesse.helpers import slice_candles
from jesse_rust import chop as chop_rust


def chop(candles: np.ndarray, period: int = 14, scalar: float = 100, drift: int = 1, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    Choppiness Index (CHOP)

    :param candles: np.ndarray
    :param period: int - default: 14
    :param scalar: float - default: 100
    :param drift: int - default: 1
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    # Preprocess candles using original slicing
    candles = slice_candles(candles, sequential)
    
    # Use Rust implementation
    res = chop_rust(candles, period, scalar, drift)
    return res if sequential else res[-1]


