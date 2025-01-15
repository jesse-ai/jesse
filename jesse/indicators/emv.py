from typing import Union
import numpy as np
from numba import njit
from jesse.helpers import same_length, slice_candles
from jesse.indicators import sma


@njit
def _emv(high: np.ndarray, low: np.ndarray, volume: np.ndarray, length, div) -> np.ndarray:
    hl2 = (high + low) / 2

    hl2_change = np.zeros_like(hl2)
    hl2_change[1:] = hl2[1:] - hl2[:-1]
    # Calculate EMV
    emv_raw = div * hl2_change * (high - low) / volume

    # Calculate SMA of EMV
    result = np.zeros_like(emv_raw)
    for i in range(length - 1, len(emv_raw)):
        result[i] = np.mean(emv_raw[i - length + 1:i + 1])

    return result


def emv(candles: np.ndarray, length: int = 14, div: int = 10000, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    EMV - Ease of Movement

    :param candles: np.ndarray
    :param length: int - default: 14
    :param div: int - default: 10000
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    high = candles[:, 3]
    low = candles[:, 4]
    volume = candles[:, 5]

    res = _emv(high, low, volume, length, div)

    return same_length(candles, res) if sequential else res[-1]
