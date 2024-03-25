from typing import Union

import numpy as np
import talib

from jesse.helpers import get_candle_source, slice_candles


def rsi(candles: np.ndarray, period: int = 14, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    RSI - Relative Strength Index

    :param candles: np.ndarray
    :param period: int - default: 14
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    r = talib.RSI(source, timeperiod=period)

    return r if sequential else r[-1]
