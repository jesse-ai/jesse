from typing import Union

import numpy as np
import talib

from jesse.helpers import get_candle_source, slice_candles


def ht_trendline(candles: np.ndarray, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    HT_TRENDLINE - Hilbert Transform - Instantaneous Trendline

    :param candles: np.ndarray
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    res = talib.HT_TRENDLINE(source)

    return res if sequential else res[-1]
