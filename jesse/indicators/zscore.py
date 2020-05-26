import numpy as np
import talib

from typing import Union


def zscore(candles: np.ndarray, period=14, matype=0, nbdev=1, sequential=False) -> Union[float, np.ndarray]:
    """
    zScore

    :param candles: np.ndarray
    :param period: int - default: 14
    :param matype: int - default: 0
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    means = talib.MA(candles[:, 2], timeperiod=period, matype=matype)
    sigmas = talib.STDDEV(candles[:, 2], timeperiod=period, nbdev=nbdev)
    zScores = (candles[:, 2] - means) / sigmas

    return zScores if sequential else zScores[-1]
