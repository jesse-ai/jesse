from typing import Union

import numpy as np

from jesse.helpers import slice_candles


def wclprice(candles: np.ndarray, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    WCLPRICE - Weighted Close Price

    :param candles: np.ndarray
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    # Calculate weighted close price as (high + low + 2*close) / 4, with high=candles[:,3], low=candles[:,4], close=candles[:,2]
    res = (candles[:,3] + candles[:,4] + 2 * candles[:,2]) / 4.0

    return res if sequential else res[-1]
