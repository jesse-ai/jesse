from typing import Union

import numpy as np
import talib


def adx(candles: np.ndarray, period=14, sequential=False) -> Union[float, np.ndarray]:
    """
    ADX - Average Directional Movement Index

    :param candles: np.ndarray
    :param period: int - default=14
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    res = talib.ADX(candles[:, 3], candles[:, 4], candles[:, 2], timeperiod=period)

    if sequential:
        return res
    else:
        return None if np.isnan(res[-1]) else res[-1]
