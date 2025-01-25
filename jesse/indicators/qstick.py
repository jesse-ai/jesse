from typing import Union

import numpy as np
from numba import njit

from jesse.helpers import same_length, slice_candles


@njit
def _qstick_fast(open_prices: np.ndarray, close_prices: np.ndarray, period: int) -> np.ndarray:
    """
    Calculate QStick values using Numba for optimization
    """
    # Pre-allocate output array
    qstick_values = np.zeros_like(open_prices, dtype=np.float64)

    # Calculate close-open difference
    diff = close_prices - open_prices

    # Calculate moving average of the difference
    for i in range(period - 1, len(diff)):
        qstick_values[i] = np.mean(diff[i - period + 1:i + 1])

    return qstick_values


def qstick(candles: np.ndarray, period: int = 5, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    QStick - Moving average of the difference between closing and opening prices

    :param candles: np.ndarray
    :param period: int - default: 5
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    res = _qstick_fast(
        np.ascontiguousarray(candles[:, 1]),  # open
        np.ascontiguousarray(candles[:, 2]),  # close
        period
    )

    return same_length(candles, res) if sequential else res[-1]
