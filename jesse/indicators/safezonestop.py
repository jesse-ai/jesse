from typing import Union

import numpy as np

from jesse.helpers import np_shift, slice_candles


def safezonestop(candles: np.ndarray, period: int = 22, mult: float = 2.5, max_lookback: int = 3,
                 direction: str = "long", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    Safezone Stops

    :param candles: np.ndarray
    :param period: int - default: 22
    :param mult: float - default: 2.5
    :param max_lookback: int - default: 3
    :param direction: str - default: long
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    high = candles[:, 3]
    low = candles[:, 4]

    last_high = np_shift(high, 1, fill_value=np.nan)
    last_low = np_shift(low, 1, fill_value=np.nan)

    diff_high = high - last_high
    diff_low = last_low - low
    diff_high = np.where(np.isnan(diff_high), 0, diff_high)
    diff_low = np.where(np.isnan(diff_low), 0, diff_low)

    raw_plus_dm = np.where((diff_high > diff_low) & (diff_high > 0), diff_high, 0)
    raw_minus_dm = np.where((diff_low > diff_high) & (diff_low > 0), diff_low, 0)

    # Vectorized Wilder smoothing using matrix operations
    def wilder_smoothing(raw: np.ndarray, period: int) -> np.ndarray:
        alpha = 1 - 1/period
        n = len(raw)
        i = np.arange(n).reshape(-1, 1)  # column vector
        j = np.arange(n).reshape(1, -1)  # row vector
        mask = (j <= i)  
        exponents = i - j
        weights = np.where(mask, alpha ** exponents, 0)
        return weights.dot(raw)

    plus_dm = wilder_smoothing(raw_plus_dm, period)
    minus_dm = wilder_smoothing(raw_minus_dm, period)

    if direction == "long":
        intermediate = last_low - mult * minus_dm
        def rolling_max(arr: np.ndarray, window: int) -> np.ndarray:
            n = len(arr)
            if n >= window:
                sw = np.lib.stride_tricks.sliding_window_view(arr, window)
                result = np.empty_like(arr)
                result[window-1:] = np.max(sw, axis=1)
                result[:window-1] = np.maximum.accumulate(arr[:window-1])
            else:
                result = np.maximum.accumulate(arr)
            return result
        
        res = rolling_max(intermediate, max_lookback)
    else:
        intermediate = last_high + mult * plus_dm
        def rolling_min(arr: np.ndarray, window: int) -> np.ndarray:
            n = len(arr)
            if n >= window:
                sw = np.lib.stride_tricks.sliding_window_view(arr, window)
                result = np.empty_like(arr)
                result[window-1:] = np.min(sw, axis=1)
                result[:window-1] = np.minimum.accumulate(arr[:window-1])
            else:
                result = np.minimum.accumulate(arr)
            return result
        
        res = rolling_min(intermediate, max_lookback)

    return res if sequential else res[-1]
