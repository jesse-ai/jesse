from typing import Union

import numpy as np
import talib

from jesse.helpers import slice_candles


def obv(candles: np.ndarray, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    OBV - On Balance Volume

    :param candles: np.ndarray
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    res = talib.OBV(candles[:, 2], candles[:, 5])

    return res if sequential else res[-1]
