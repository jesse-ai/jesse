from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, slice_candles


def roc(candles: np.ndarray, period: int = 10, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    ROC - Rate of change : ((price/prevPrice)-1)*100

    :param candles: np.ndarray
    :param period: int - default: 10
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    n = len(source)
    res = np.full(n, np.nan, dtype=float)
    if n > period:
        res[period:] = (source[period:] / source[:-period] - 1) * 100

    return res if sequential else res[-1]
