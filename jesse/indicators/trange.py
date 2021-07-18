from typing import Union

import numpy as np
import talib

from jesse.helpers import slice_candles


def trange(candles: np.ndarray, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    TRANGE - True Range

    :param candles: np.ndarray
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    res = talib.TRANGE(candles[:, 3], candles[:, 4], candles[:, 2])

    return res if sequential else res[-1]
