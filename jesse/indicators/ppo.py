from typing import Union

import numpy as np
import talib

from jesse.helpers import get_candle_source
from jesse.helpers import slice_candles


def ppo(candles: np.ndarray, fast_period: int = 12, slow_period: int = 26, matype: int = 0, source_type: str = "close",
        sequential: bool = False) -> Union[float, np.ndarray]:
    """
    PPO - Percentage Price Oscillator

    :param candles: np.ndarray
    :param fast_period: int - default: 12
    :param slow_period: int - default: 26
    :param matype: int - default: 0
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    res = talib.PPO(source, fastperiod=fast_period, slowperiod=slow_period, matype=matype)

    return res if sequential else res[-1]
