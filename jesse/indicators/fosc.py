from typing import Union
import numpy as np
from jesse.helpers import get_candle_source, same_length, slice_candles
from numba import njit


@njit
def linear_regression_line(x, y):
    n = len(x)
    sum_x = np.sum(x)
    sum_y = np.sum(y)
    sum_xy = np.sum(x * y)
    sum_xx = np.sum(x * x)

    slope = (n * sum_xy - sum_x * sum_y) / (n * sum_xx - sum_x * sum_x)
    intercept = (sum_y - slope * sum_x) / n

    return slope * x + intercept


def fosc(candles: np.ndarray, period: int = 5, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    FOSC - Forecast Oscillator

    :param candles: np.ndarray
    :param period: int - default: 5
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)
    source = get_candle_source(candles, source_type=source_type)

    # Prepare the result array
    res = np.zeros_like(source)

    # Calculate FOSC for each window
    for i in range(period - 1, len(source)):
        window = source[i - period + 1:i + 1]
        x = np.arange(period)
        predicted = linear_regression_line(x, window)
        res[i] = 100 * (window[-1] - predicted[-1]) / window[-1]

    # Replace initial NaN values with 0
    res[:period - 1] = 0

    return same_length(candles, res) if sequential else res[-1]
