from typing import Union
import numpy as np
from jesse.helpers import get_candle_source, slice_candles
from jesse_rust import kama as kama_rust


def kama(candles: np.ndarray, period: int = 14, fast_length: int = 2, slow_length: int = 30, 
         source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    KAMA - Kaufman Adaptive Moving Average
    
    :param candles: np.ndarray
    :param period: int - default: 14, lookback period for the calculation
    :param fast_length: int - default: 2, fast EMA length for smoothing factor
    :param slow_length: int - default: 30, slow EMA length for smoothing factor
    :param source_type: str - default: "close", specifies the candle field
    :param sequential: bool - default: False, if True returns the full array, otherwise only the last value

    :return: float | np.ndarray
    """
    if candles.ndim == 1:
        src = candles
    else:
        candles = slice_candles(candles, sequential)
        src = get_candle_source(candles, source_type=source_type)

    src = np.asarray(src, dtype=np.float64)
    
    result = kama_rust(src, period, fast_length, slow_length)
    
    return result if sequential else result[-1]
