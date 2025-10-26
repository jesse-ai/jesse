from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, slice_candles
from jesse_rust import ema as ema_rust


def ema(candles: np.ndarray, period: int = 5, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    EMA - Exponential Moving Average using Numba for optimization

    :param candles: np.ndarray
    :param period: int - default: 5
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    result = ema_rust(source, period)
    return result if sequential else result[-1]
