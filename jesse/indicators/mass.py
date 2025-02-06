from typing import Union

import numpy as np
from numba import njit

from jesse.helpers import same_length, slice_candles
from jesse.indicators.ema import ema


def mass(candles: np.ndarray, period: int = 5, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    MASS - Mass Index
    The Mass Index uses the high-low range to identify trend reversals based on range expansions.
    It suggests that a reversal of the current trend may be imminent when the range widens beyond 
    a certain point and then contracts.

    :param candles: np.ndarray
    :param period: int - default: 5
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    # Calculate high-low range
    high_low_range = candles[:, 3] - candles[:, 4]  # high - low

    # Calculate 9-period EMA of high-low range
    ema1 = ema(high_low_range, period=9, sequential=True)

    # Calculate 9-period EMA of the first EMA
    ema2 = ema(ema1, period=9, sequential=True)

    # Calculate EMA ratio
    ratio = np.divide(ema1, ema2, out=np.zeros_like(ema1), where=ema2 != 0)

    # Calculate period-sum of ratio using Numba for optimization
    res = mass_sum(ratio, period)

    return same_length(candles, res) if sequential else res[-1]


@njit(cache=True)
def mass_sum(ratio: np.ndarray, period: int) -> np.ndarray:
    """Calculate the sum of the ratio over the specified period"""
    result = np.zeros_like(ratio)
    for i in range(period - 1, len(ratio)):
        result[i] = np.sum(ratio[i-period+1:i+1])
    return result
