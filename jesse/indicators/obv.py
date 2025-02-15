from typing import Union

import numpy as np

from jesse.helpers import slice_candles


def obv(candles: np.ndarray, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    OBV - On Balance Volume

    :param candles: np.ndarray
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    close = candles[:, 2]
    volume = candles[:, 5]
    # Compute the change in OBV: add volume if price increases, subtract if decreases, else 0
    delta = np.where(close[1:] > close[:-1], volume[1:], np.where(close[1:] < close[:-1], -volume[1:], 0))
    obv_arr = np.empty_like(volume, dtype=np.float64)
    obv_arr[0] = volume[0]
    if len(volume) > 1:
        obv_arr[1:] = volume[0] + np.cumsum(delta)
    return obv_arr if sequential else obv_arr[-1]
