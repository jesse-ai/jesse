import numpy as np
import talib

from typing import Union


def roc(candles: np.ndarray, period=10, sequential=False) -> Union[float, np.ndarray]:
    """
    ROC - Rate of change : ((price/prevPrice)-1)*100

    :param candles: np.ndarray
    :param period: int - default=10
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    res = talib.ROC(candles[:, 2], timeperiod=period)

    if sequential:
        return res
    else:
        return None if np.isnan(res[-1]) else res[-1]
