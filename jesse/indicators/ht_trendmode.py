from typing import Union

import numpy as np
import talib

from jesse.helpers import get_candle_source


def ht_trendmode(candles: np.ndarray, source_type="close", sequential=False) -> Union[float, np.ndarray]:
    """
    HT_TRENDMODE - Hilbert Transform - Trend vs Cycle Mode

    :param candles: np.ndarray
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: int | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)
    res = talib.HT_TRENDMODE(source)

    return res if sequential else res[-1]
