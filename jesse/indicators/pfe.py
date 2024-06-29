from typing import Union

import numpy as np
import talib

from jesse.helpers import get_candle_source, same_length, slice_candles


def pfe(candles: np.ndarray, period: int = 10, smoothing: int = 5, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    Polarized Fractal Efficiency (PFE)

    :param candles: np.ndarray
    :param period: int - default: 10
    :param smoothing: int - default: 5
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)

    ln = period - 1
    diff = np.diff(source, ln)
    a = np.sqrt(np.power(diff, 2) + np.power(period, 2))
    b = talib.SUM(np.sqrt(1 + np.power(np.diff(source, 1), 2)), ln)
    pfetmp = 100 * same_length(source, a) / same_length(source, b)
    res = talib.EMA(np.where(same_length(source, diff) > 0, pfetmp, -pfetmp), smoothing)

    return res if sequential else res[-1]
