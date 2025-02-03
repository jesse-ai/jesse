from typing import Union

import numpy as np
from numba import njit

from jesse.helpers import get_candle_source, same_length, slice_candles


def efi(candles: np.ndarray, period: int = 13, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    EFI - Elders Force Index

    :param candles: np.ndarray
    :param period: int - default: 13
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)

    dif = efi_fast(source, candles[:, 5])

    res = ema(dif, period)
    res_with_nan = same_length(candles, res)

    return res_with_nan if sequential else res_with_nan[-1]


@njit(cache=True)
def efi_fast(source, volume):
    dif = np.zeros(source.size - 1)
    for i in range(1, source.size):
        dif[i - 1] = (source[i] - source[i - 1]) * volume[i]
    return dif


def ema(data: np.ndarray, period: int) -> np.ndarray:
    alpha = 2.0 / (period + 1)
    n = data.shape[0]
    out = np.full(n, np.nan)
    if n < period:
        return out
    seed = np.mean(data[:period])
    out[period - 1] = seed
    m = n - period  # number of elements beyond the seed
    if m > 0:
        # Create indices for the subsequent calculations
        indices = np.arange(1, m + 1)  # i from 1 to m, corresponds to t = period-1 + i
        j = np.arange(m)               # j from 0 to m-1
        # Compute exponent matrix where each element [i, j] = (1 - alpha)^(i - 1 - j) for j < i, else 0
        exp_matrix = indices[:, None] - 1 - j[None, :]
        mask = j[None, :] < indices[:, None]
        W = np.where(mask, (1 - alpha) ** exp_matrix, 0.0)
        # data_slice holds the data for indices from period to end
        data_slice = data[period:period + m]
        # Compute the weighted sum for each row
        weighted_sums = np.sum(W * data_slice, axis=1)
        ema_values = (1 - alpha) ** indices * seed + alpha * weighted_sums
        out[period:] = ema_values
    return out
