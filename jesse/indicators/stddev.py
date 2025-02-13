from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, slice_candles


def stddev(candles: np.ndarray, period: int = 5, nbdev: float = 1, source_type: str = "close",
           sequential: bool = False) -> Union[float, np.ndarray]:
    """
    STDDEV - Standard Deviation

    :param candles: np.ndarray
    :param period: int - default: 5
    :param nbdev: float - default: 1
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    n = len(source)
    # Initialize result array with nan values
    result = np.full(n, np.nan, dtype=float)

    if n < period:
        # Not enough data for full period, result remains as nans
        output = result
    else:
        # Create rolling windows using numpy's sliding_window_view
        windows = np.lib.stride_tricks.sliding_window_view(source, window_shape=period)
        # Compute standard deviation over the rolling windows using population std (ddof=0) and multiply by nbdev
        rolling_std = np.std(windows, axis=1, ddof=0) * nbdev
        # Fill the result array from index 'period - 1' onward with the computed rolling std
        result[period - 1:] = rolling_std
        output = result

    return output if sequential else output[-1]
