from typing import Union

import numpy as np

from jesse.helpers import slice_candles
from jesse_rust import willr as willr_rust


def willr(candles: np.ndarray, period: int = 14, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    WILLR - Williams' %R

    :param candles: np.ndarray
    :param period: int - default: 14
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)
    
    # Convert to float64 for Rust compatibility
    candles_f64 = np.asarray(candles, dtype=np.float64)
    
    # Call the Rust implementation
    result = willr_rust(candles_f64, period)
    
    return result if sequential else result[-1]
