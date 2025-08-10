import numpy as np
from typing import Union

from jesse.helpers import get_candle_source, slice_candles
from jesse_rust import rsi as rsi_rust


def rsi(candles: np.ndarray, period: int = 14, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    RSI - Relative Strength Index

    :param candles: np.ndarray
    :param period: int - default: 14
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    p = np.asarray(source, dtype=np.float64)
    result = rsi_rust(p, period)
    return result if sequential else result[-1]
