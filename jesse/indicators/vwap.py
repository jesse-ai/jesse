from typing import Union

import numpy as np
from numba import njit

from jesse.helpers import get_candle_source
from jesse.helpers import get_config


def vwap(candles: np.ndarray, source_type: str = "hlc3", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    VWAP

    :param candles: np.ndarray
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

    source = get_candle_source(candles, source_type=source_type)

    res = np_vwap(source, candles[:, 5])

    if sequential:
        return res
    else:
        return None if np.isnan(res[-1]) else res[-1]


@njit
def np_vwap(source, volume):
    return np.cumsum(volume * source) / np.cumsum(volume)
