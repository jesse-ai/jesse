from typing import Union

import numpy as np
import talib

from jesse.helpers import get_candle_source
from jesse.helpers import slice_candles


def stc(candles: np.ndarray, fast_period: int = 23, fast_matype: int = 1, slow_period: int = 50, slow_matype: int = 1,
        k_period: int = 10, d_period: int = 3,
        source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    STC - Schaff Trend Cycle (Oscillator)

    :param candles: np.ndarray
    :param fast_period: int - default: 23
    :param fastmatype: int - default: 1
    :param slow_period: int - default: 50
    :param slowmatype: int - default: 1
    :param k_period: int - default: 10
    :param d_period: int - default: 3
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)

    macd, macdsignal, macdhist = talib.MACDEXT(source, fastperiod=fast_period, fastmatype=fast_matype,
                                               slowperiod=slow_period, slowmatype=slow_matype)

    stok = (macd - talib.MIN(macd, k_period)) / (talib.MAX(macd, k_period) - talib.MIN(macd, k_period)) * 100

    d = talib.EMA(stok, d_period)

    kd = (d - talib.MIN(d, k_period)) / (talib.MAX(d, k_period) - talib.MIN(d, k_period)) * 100

    res = talib.EMA(kd, d_period)

    return res if sequential else res[-1]
