from typing import Union

import numpy as np
import talib


def obv(candles: np.ndarray, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    OBV - On Balance Volume

    :param candles: np.ndarray
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    res = talib.OBV(candles[:, 2], candles[:, 5])

    if sequential:
        return res
    else:
        return None if np.isnan(res[-1]) else res[-1]
