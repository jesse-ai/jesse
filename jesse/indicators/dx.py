from typing import Union

import numpy as np
import talib

from jesse.helpers import slice_candles


def dx(candles: np.ndarray, period: int = 14, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    DX - Directional Movement Index

    :param candles: np.ndarray
    :param period: int - default: 14
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    res = talib.DX(candles[:, 3], candles[:, 4], candles[:, 2], timeperiod=period)

    return res if sequential else res[-1]
