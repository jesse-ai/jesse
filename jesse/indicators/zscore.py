from typing import Union

import numpy as np
import talib

from jesse.helpers import get_candle_source


def zscore(candles: np.ndarray, period: int = 14, ma_type: int = 0, nbdev: float = 1, source_type: str = "close",
           sequential: bool = False) -> Union[float, np.ndarray]:
    """
    zScore

    :param candles: np.ndarray
    :param period: int - default: 14
    :param ma_type: int - default: 0
    :param nbdev: float - default: 1
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)
    means = talib.MA(source, timeperiod=period, ma_type=ma_type)
    sigmas = talib.STDDEV(source, timeperiod=period, nbdev=nbdev)
    zScores = (source - means) / sigmas

    return zScores if sequential else zScores[-1]
