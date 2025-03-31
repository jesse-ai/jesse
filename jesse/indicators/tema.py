from typing import Union

import numpy as np
from numba import njit
from jesse.helpers import get_candle_source, slice_candles

@njit(cache=True)
def _ema(source: np.ndarray, period: int) -> np.ndarray:
    alpha = 2.0 / (period + 1.0)
    result = np.zeros_like(source)
    result[0] = source[0]
    
    for i in range(1, len(source)):
        result[i] = alpha * source[i] + (1 - alpha) * result[i-1]
        
    return result

def tema(candles: np.ndarray, period: int = 9, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    TEMA - Triple Exponential Moving Average

    :param candles: np.ndarray
    :param period: int - default: 9
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    ema1 = _ema(source, period)
    ema2 = _ema(ema1, period)
    ema3 = _ema(ema2, period)
    res = 3 * ema1 - 3 * ema2 + ema3
    
    return res if sequential else res[-1]

