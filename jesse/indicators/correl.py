from typing import Union

import numpy as np

from jesse.helpers import slice_candles


def correl(candles: np.ndarray, period: int = 5, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    CORREL - Pearson's Correlation Coefficient (r)

    :param candles: np.ndarray
    :param period: int - default: 5
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)
    x = candles[:, 3]
    y = candles[:, 4]
    n = len(x)
    
    # If not enough data, return an array of NaNs
    if n < period:
        res = np.empty(n)
        res[:] = np.nan
        return res if sequential else res[-1]

    # Use numpy's sliding_window_view for vectorized rolling window computation
    windows_x = np.lib.stride_tricks.sliding_window_view(x, window_shape=period)
    windows_y = np.lib.stride_tricks.sliding_window_view(y, window_shape=period)
    
    mean_x = np.mean(windows_x, axis=1)
    mean_y = np.mean(windows_y, axis=1)
    
    # Calculate numerator and denominator for Pearson correlation coefficient
    numerator = np.sum((windows_x - mean_x[:, None]) * (windows_y - mean_y[:, None]), axis=1)
    denominator = np.sqrt(np.sum((windows_x - mean_x[:, None])**2, axis=1) * np.sum((windows_y - mean_y[:, None])**2, axis=1))
    
    with np.errstate(divide='ignore', invalid='ignore'):
        corr_vals = numerator / denominator
    
    # Prepare full result array with initial NaNs for indices with insufficient data
    res_full = np.empty(n)
    res_full[:period-1] = np.nan
    res_full[period-1:] = corr_vals
    
    return res_full if sequential else res_full[-1]
