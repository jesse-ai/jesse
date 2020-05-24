import numpy as np
import talib

from collections import namedtuple

BollingerBands = namedtuple('BollingerBands', ['upperband', 'middleband', 'lowerband'])


def bollinger_bands(candles: np.ndarray, period=20, devup=2, devdn=2, matype=0, sequential=False) -> BollingerBands:
    """
    BBANDS - Bollinger Bands

    :param candles: np.ndarray
    :param period: int - default: 20
    :param devup: float - default: 2
    :param devdn: float - default: 2
    :param matype: int - default: 0
    :param sequential: bool - default=False

    :return: BollingerBands
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    upperbands, middlebands, lowerbands = talib.BBANDS(candles[:, 2], timeperiod=period, nbdevup=devup, nbdevdn=2, matype=matype)

    if sequential:
        return BollingerBands(upperbands, middlebands, lowerbands)
    else:
        return BollingerBands(upperbands[-1], middlebands[-1], lowerbands[-1])
