from typing import Union

import numpy as np
from numba import njit

from jesse.helpers import get_candle_source
from jesse.helpers import get_config


def cg(candles: np.ndarray, period: int = 10, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    Center of Gravity (CG)

    :param candles: np.ndarray
    :param period: int - default: 10
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

    source = get_candle_source(candles, source_type=source_type)
    res = go_fast(source, period)

    return np.concatenate((np.full((candles.shape[0] - res.shape[0]), np.nan), res), axis=0) if sequential else res[-1]


@njit
def go_fast(source, period):  # Function is compiled to machine code when called the first time
    res = np.full_like(source, fill_value=np.nan)
    for i in range(0, len(source)):
        if i > period:
            num = 0
            denom = 0
            for count in range(0, period - 1):
                close = source[i - count]
                if not np.isnan(close):
                    num = num + (1 + count) * close
                    denom = denom + close
            result = -num / denom if denom != 0 else 0
            res[i] = result
    return res
