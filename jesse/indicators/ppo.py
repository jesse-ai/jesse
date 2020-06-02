from typing import Union

import numpy as np
import talib

from jesse.helpers import get_candle_source


def ppo(candles: np.ndarray, fastperiod=12, slowperiod=26, matype=0, source_type="close", sequential=False) -> Union[
    float, np.ndarray]:
    """
    PPO - Percentage Price Oscillator

    :param candles: np.ndarray
    :param fastperiod: int - default: 12
    :param slowperiod: int - default: 26
    :param matype: int - default: 0
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)
    res = talib.PPO(source, fastperiod=fastperiod, slowperiod=slowperiod, matype=matype)

    return res if sequential else res[-1]
