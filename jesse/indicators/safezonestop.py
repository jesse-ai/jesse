from typing import Union

import numpy as np
import talib
from numpy.lib.stride_tricks import sliding_window_view

from jesse.helpers import np_shift, get_config


def safezonestop(candles: np.ndarray, period: int = 22, mult: float = 2.5, max_lookback: int = 3,
                 direction: str = "long", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    Safezone Stops

    :param candles: np.ndarray
    :param period: int - default=22
    :param mult: float - default=2.5
    :param max_lookback: int - default=3
    :param direction: str - default=long
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

    high = candles[:, 3]
    low = candles[:, 4]

    last_high = np_shift(high, 1, fill_value=np.nan)
    last_low = np_shift(low, 1, fill_value=np.nan)

    if direction == "long":
        res = last_low - mult * talib.MINUS_DM(high, low, timeperiod=period)
        swv = sliding_window_view(res, window_shape=max_lookback)
        res = np.max(swv, axis=-1)
    else:
        res = last_high + mult * talib.PLUS_DM(high, low, timeperiod=period)
        swv = sliding_window_view(res, window_shape=max_lookback)
        res = np.min(swv, axis=-1)

    return np.concatenate((np.full((candles.shape[0] - res.shape[0]), np.nan), res), axis=0) if sequential else res[-1]
