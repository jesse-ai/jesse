from typing import Union

import numpy as np

from jesse.helpers import slice_candles


def adx(candles: np.ndarray, period: int = 14, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    ADX - Average Directional Movement Index using vectorized matrix operations for smoothing.

    :param candles: np.ndarray, expected 2D array with OHLCV data where index 3 is high, index 4 is low, and index 2 is close
    :param period: int - default: 14
    :param sequential: bool - if True, return full series, else return last value
    :return: float | np.ndarray
    """
    if len(candles.shape) < 2:
        raise ValueError("adx indicator requires a 2D array of candles")
    candles = slice_candles(candles, sequential)

    high = candles[:, 3]
    low = candles[:, 4]
    close = candles[:, 2]
    n = len(close)
    if n <= period:
        return np.nan if sequential else np.nan

    # Initialize arrays
    TR = np.zeros(n)
    plusDM = np.zeros(n)
    minusDM = np.zeros(n)

    # Vectorized True Range computation for indices 1 to n-1
    true_range = np.maximum(
        np.maximum(high[1:] - low[1:], np.abs(high[1:] - close[:-1])),
        np.abs(low[1:] - close[:-1])
    )
    TR[1:] = true_range

    # Directional movements
    diff_high = high[1:] - high[:-1]
    diff_low = low[:-1] - low[1:]
    plusDM[1:] = np.where((diff_high > diff_low) & (diff_high > 0), diff_high, 0)
    minusDM[1:] = np.where((diff_low > diff_high) & (diff_low > 0), diff_low, 0)

    # Wilder's smoothing parameters
    a = 1 / period
    discount = 1 - a

    # Vectorized Wilder smoothing using matrix operations
    def wilder_smooth(arr):
        S = np.empty(n)
        S[:period] = np.nan
        init = np.sum(arr[1:period+1])
        S[period] = init
        M = n - period - 1  # number of elements to smooth after index 'period'
        if M > 0:
            X = arr[period+1:]
            # Construct lower-triangular matrix where element (i, j) = discount^(i - j) for i >= j
            T = np.tril(np.power(discount, np.subtract.outer(np.arange(M), np.arange(M))))
            offsets = np.arange(1, M + 1)  # discount exponent for the initial term
            S[period+1:] = init * (discount ** offsets) + a * (T @ X)
        return S

    tr_smoothed = wilder_smooth(TR)
    plusDM_smoothed = wilder_smooth(plusDM)
    minusDM_smoothed = wilder_smooth(minusDM)

    # Compute DI+ and DI-
    DI_plus = np.full(n, np.nan)
    DI_minus = np.full(n, np.nan)
    valid = np.arange(period, n)
    DI_plus[valid] = np.where(tr_smoothed[valid] == 0, 0, 100 * plusDM_smoothed[valid] / tr_smoothed[valid])
    DI_minus[valid] = np.where(tr_smoothed[valid] == 0, 0, 100 * minusDM_smoothed[valid] / tr_smoothed[valid])
    dd = DI_plus[valid] + DI_minus[valid]
    DX = np.full(n, np.nan)
    DX[valid] = np.where(dd == 0, 0, 100 * np.abs(DI_plus[valid] - DI_minus[valid]) / dd)

    # Compute ADX smoothing
    ADX = np.full(n, np.nan)
    start_index = period * 2
    if start_index < n:
        first_adx = np.mean(DX[period:start_index])
        ADX[start_index] = first_adx
        M_adx = n - start_index - 1
        if M_adx > 0:
            Y = DX[start_index+1:]
            T_adx = np.tril(np.power(discount, np.subtract.outer(np.arange(M_adx), np.arange(M_adx))))
            offsets_adx = np.arange(1, M_adx + 1)
            ADX[start_index+1:] = first_adx * (discount ** offsets_adx) + a * (T_adx @ Y)
    result = ADX if sequential else ADX[-1]
    return result
