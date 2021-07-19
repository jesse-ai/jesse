from typing import Union

import numpy as np
import talib

from jesse.helpers import slice_candles


def medprice(candles: np.ndarray, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    MEDPRICE - Median Price

    :param candles: np.ndarray
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    res = talib.MEDPRICE(candles[:, 3], candles[:, 4])

    return res if sequential else res[-1]
