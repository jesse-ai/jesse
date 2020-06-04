from typing import Union

import numpy as np
import talib

from jesse.helpers import get_candle_source


def zscore(candles: np.ndarray, period=14, matype=0, nbdev=1, source_type="close", sequential=False) -> Union[
    float, np.ndarray]:
    """
    zScore

    :param candles: np.ndarray
    :param period: int - default: 14
    :param matype: int - default: 0
    :param nbdev: int - default: 1
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)
    means = talib.MA(source, timeperiod=period, matype=matype)
    sigmas = talib.STDDEV(source, timeperiod=period, nbdev=nbdev)
    zScores = (source - means) / sigmas

    return zScores if sequential else zScores[-1]
