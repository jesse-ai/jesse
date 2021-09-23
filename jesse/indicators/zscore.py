from typing import Union

import numpy as np
import talib
from jesse.indicators.ma import ma
from jesse.indicators.mean_ad import mean_ad
from jesse.indicators.median_ad import median_ad

from jesse.helpers import get_candle_source
from jesse.helpers import slice_candles


def zscore(candles: np.ndarray, period: int = 14, matype: int = 0, nbdev: float = 1, devtype: int = 0, source_type: str = "close",
           sequential: bool = False) -> Union[float, np.ndarray]:
    """
    zScore

    :param candles: np.ndarray
    :param period: int - default: 14
    :param matype: int - default: 0
    :param nbdev: float - default: 1
    :param devtype: int - default: 0
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    means = ma(source, period=period, matype=matype, sequential=True)

    if devtype == 0:
       sigmas = talib.STDDEV(source, period) * nbdev
    elif devtype == 1:
       sigmas = mean_ad(source, period, sequential=True) * nbdev
    elif devtype == 2:
       sigmas = median_ad(source, period, sequential=True) * nbdev

    zScores = (source - means) / sigmas

    return zScores if sequential else zScores[-1]
