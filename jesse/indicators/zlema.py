from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, same_length, slice_candles
import jesse_rust


def zlema(candles: np.ndarray, period: int = 20, source_type: str = "close", sequential: bool = False) -> Union[
        float, np.ndarray]:
    """
    Zero-Lag Exponential Moving Average

    :param candles: np.ndarray
    :param period: int - default: 20
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)
        
    # Use the Rust implementation
    res = jesse_rust.zlema(source, period)

    return same_length(candles, res) if sequential else res[-1]
