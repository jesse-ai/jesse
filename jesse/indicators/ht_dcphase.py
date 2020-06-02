from typing import Union

import numpy as np
import talib

from jesse.helpers import get_candle_source


def ht_dcphase(candles: np.ndarray, source_type="close", sequential=False) -> Union[float, np.ndarray]:
    """
    HT_DCPHASE - Hilbert Transform - Dominant Cycle Phase

    :param candles: np.ndarray
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)
    res = talib.HT_DCPHASE (source)

    return res if sequential else res[-1]
