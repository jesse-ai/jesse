import numpy as np
import talib

from typing import Union


def apo(candles: np.ndarray, fastperiod=12, slowperiod=26, matype=0, sequential=False) -> Union[float, np.ndarray]:
    """
    APO - Absolute Price Oscillator

    :param candles: np.ndarray
    :param fastperiod: int - default: 12
    :param slowperiod: int - default: 26
    :param matype: int - default: 0
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    res = talib.APO(candles[:, 2], fastperiod=fastperiod, slowperiod=slowperiod, matype=matype)

    return res if sequential else res[-1]
