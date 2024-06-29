from typing import Union

import numpy as np
import talib

from jesse.helpers import slice_candles


def beta(candles: np.ndarray, benchmark_candles: np.ndarray, period: int = 5, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    BETA - compares the given candles close price to its benchmark (should be in the same time frame)

    :param candles: np.ndarray
    :param benchmark_candles: np.ndarray
    :param period: int - default: 5
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)
    benchmark_candles = slice_candles(benchmark_candles, sequential)

    res = talib.BETA(candles[:, 2], benchmark_candles[:, 2], timeperiod=period)

    return res if sequential else res[-1]
