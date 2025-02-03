from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, slice_candles


def kama(candles: np.ndarray, period: int = 14, fast_length: int = 2, slow_length: int = 30, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    KAMA - Kaufman Adaptive Moving Average
    
    :param candles: np.ndarray
    :param period: int - default: 14, lookback period for the calculation
    :param fast_length: int - default: 2, fast EMA length for smoothing factor
    :param slow_length: int - default: 30, slow EMA length for smoothing factor
    :param source_type: str - default: "close", specifies the candle field
    :param sequential: bool - default: False, if True returns the full array, otherwise only the last value

    :return: float | np.ndarray
    """
    if candles.ndim == 1:
        src = candles
    else:
        candles = slice_candles(candles, sequential)
        src = get_candle_source(candles, source_type=source_type)

    src = np.asarray(src)
    n = len(src)
    
    # If not enough data, return the source
    if n <= period:
        return src if sequential else src[-1]

    # m: number of points computed with the recursive formula
    m = n - period

    # Vectorized momentum and volatility
    momentum = np.abs(src[period:] - src[:-period])  # shape (m,)
    diff_array = np.abs(np.diff(src))  # shape (n-1,)
    volatility = np.convolve(diff_array, np.ones(period, dtype=diff_array.dtype), mode='valid')  # shape (m,)
    er = np.where(volatility != 0, momentum / volatility, 0.0)  # shape (m,)

    fast_alpha = 2 / (fast_length + 1)
    slow_alpha = 2 / (slow_length + 1)
    A_vec = (er * (fast_alpha - slow_alpha) + slow_alpha) ** 2  # shape (m,)

    # Compute the matrix-based solution of the recursion:
    # For indices i from 0 to m-1 (corresponding to overall index period+i), we have:
    #   kama[period+i] = sum_{j=0}^{i} [ weight_matrix[i, j] * (A_vec[j] * src[period+j]) ] + base_term[i]
    # where weight_matrix is a lower-triangular matrix computed using cumulative logs to represent the products of (1 - A_vec).
    B = 1 - A_vec
    eps = 1e-10
    c = np.concatenate(([0.0], np.cumsum(np.log(B + eps))))  # shape (m+1,)
    c_row = c[1:].reshape(-1, 1)  # shape (m, 1)
    c_col = c[1:].reshape(1, -1)  # shape (1, m)
    weight_matrix = np.exp(c_row - c_col)  # shape (m, m)
    weight_matrix = np.tril(weight_matrix)  # keep only lower-triangular elements

    X = A_vec * src[period:]  # shape (m,)
    weighted_sum = np.sum(weight_matrix * X.reshape(1, m), axis=1)  # shape (m,)

    base_term = np.exp(c[1:]) * src[period-1]  # shape (m,)

    kama_computed = weighted_sum + base_term  # shape (m,)

    result = np.empty(n, dtype=float)
    result[:period] = src[:period]
    result[period:] = kama_computed

    return result if sequential else result[-1]
