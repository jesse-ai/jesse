from typing import Union

import numpy as np
import talib

from jesse.helpers import get_candle_source


def apo(candles: np.ndarray, fast_period=12, slow_period=26, ma_type=0, source_type: str ="close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    APO - Absolute Price Oscillator

    :param candles: np.ndarray
    :param fast_period: int - default: 12
    :param slow_period: int - default: 26
    :param ma_type: int - default: 0
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)

    res = talib.APO(source, fast_period=fast_period, slow_period=slow_period, ma_type=ma_type)

    return res if sequential else res[-1]
