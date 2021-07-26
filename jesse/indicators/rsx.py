from typing import Union

import numpy as np
try:
    from numba import njit
except ImportError:
    njit = lambda a : a

from jesse.helpers import get_candle_source, slice_candles


def rsx(candles: np.ndarray, period: int = 14, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    Relative Strength Xtra (rsx)
   
    :param candles: np.ndarray
    :param period: int - default: 14
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    res = rsx_fast(source, period)

    return res if sequential else res[-1]


@njit
def rsx_fast(source, period):
    # variables
    f0 = 0
    f8 = 0
    # f10 = 0
    f18 = 0
    f20 = 0
    f28 = 0
    f30 = 0
    f38 = 0
    f40 = 0
    f48 = 0
    f50 = 0
    f58 = 0
    f60 = 0
    f68 = 0
    f70 = 0
    f78 = 0
    f80 = 0
    f88 = 0
    f90 = 0

    # v4 = 0
    # v8 = 0
    # v10 = 0
    v14 = 0
    # v18 = 0
    v20 = 0

    # vC = 0
    # v1C = 0

    res = np.full_like(source, np.nan)

    for i in range(period, source.size):
        if f90 == 0:
            f90 = 1.0
            f0 = 0.0
            f88 = period - 1.0 if period >= 6 else 5.0
            f8 = 100.0 * source[i]
            f18 = 3.0 / (period + 2.0)
            f20 = 1.0 - f18
        else:
            f90 = f88 + 1 if f88 <= f90 else f90 + 1
            f10 = f8
            f8 = 100 * source[i]
            v8 = f8 - f10
            f28 = f20 * f28 + f18 * v8
            f30 = f18 * f28 + f20 * f30
            vC = f28 * 1.5 - f30 * 0.5
            f38 = f20 * f38 + f18 * vC
            f40 = f18 * f38 + f20 * f40
            v10 = f38 * 1.5 - f40 * 0.5
            f48 = f20 * f48 + f18 * v10
            f50 = f18 * f48 + f20 * f50
            v14 = f48 * 1.5 - f50 * 0.5
            f58 = f20 * f58 + f18 * abs(v8)
            f60 = f18 * f58 + f20 * f60
            v18 = f58 * 1.5 - f60 * 0.5
            f68 = f20 * f68 + f18 * v18
            f70 = f18 * f68 + f20 * f70
            v1C = f68 * 1.5 - f70 * 0.5
            f78 = f20 * f78 + f18 * v1C
            f80 = f18 * f78 + f20 * f80
            v20 = f78 * 1.5 - f80 * 0.5
            if f88 >= f90 and f8 != f10:
                f0 = 1.0
            if f88 == f90 and f0 == 0.0:
                f90 = 0.0
        if f88 < f90 and v20 > 0.0000000001:
            v4 = (v14 / v20 + 1.0) * 50.0
            v4 = min(v4, 100.0)
            v4 = max(v4, 0.0)
        else:
            v4 = 50.0
        res[i] = v4
    return res
