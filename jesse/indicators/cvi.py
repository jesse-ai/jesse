from typing import Union
import numpy as np
from numba import njit
import jesse.helpers as jh
from jesse.indicators.ema import ema


@njit
def _calculate_cvi(ema_diff: np.ndarray, period: int) -> np.ndarray:
    # Calculate rate of change
    result = np.zeros_like(ema_diff)
    result[period:] = ((ema_diff[period:] - ema_diff[:-period]) / ema_diff[:-period]) * 100
    return result


def cvi(candles: np.ndarray, period: int = 5, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    CVI - Chaikins Volatility

    :param candles: np.ndarray
    :param period: int - default: 5
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = jh.slice_candles(candles, sequential)

    high = np.ascontiguousarray(candles[:, 3])
    low = np.ascontiguousarray(candles[:, 4])

    # Calculate high-low difference
    hl_diff = high - low

    # Calculate EMA of the difference using existing EMA indicator
    ema_diff = ema(hl_diff, period, sequential=True)

    res = _calculate_cvi(ema_diff, period)

    return jh.same_length(candles, res) if sequential else res[-1]
