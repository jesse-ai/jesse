from typing import Union

import numpy as np
import talib


def medprice(candles: np.ndarray, sequential=False) -> Union[float, np.ndarray]:
    """
    MEDPRICE - Median Price

    :param candles: np.ndarray
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    res = talib.MEDPRICE(candles[:, 3], candles[:, 4])

    if sequential:
        return res
    else:
        return None if np.isnan(res[-1]) else res[-1]
