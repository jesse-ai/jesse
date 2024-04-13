from typing import Union

import numpy as np
import talib
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

    res = talib.EMA(dif, timeperiod=period)
    res_with_nan = same_length(candles, res)

    return res_with_nan if sequential else res_with_nan[-1]


@njit(cache=True)
def efi_fast(source, volume):
    dif = np.zeros(source.size - 1)
    for i in range(1, source.size):
        dif[i - 1] = (source[i] - source[i - 1]) * volume[i]
    return dif
