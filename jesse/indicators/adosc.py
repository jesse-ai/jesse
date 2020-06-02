from typing import Union

import numpy as np
import talib


def adosc(candles: np.ndarray, fastperiod=3, slowperiod=10, sequential=False) -> Union[float, np.ndarray]:
    """
    ADOSC - Chaikin A/D Oscillator

    :param candles: np.ndarray
    :param fastperiod: int - default: 3
    :param slowperiod: int - default: 10
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    res = talib.ADOSC(candles[:, 3], candles[:, 4], candles[:, 2], candles[:, 5], fastperiod=fastperiod,
                      slowperiod=slowperiod)

    if sequential:
        return res
    else:
        return None if np.isnan(res[-1]) else res[-1]
