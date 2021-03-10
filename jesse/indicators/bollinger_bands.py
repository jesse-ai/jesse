from collections import namedtuple

import numpy as np
import talib

from jesse.helpers import get_candle_source, slice_candles

BollingerBands = namedtuple('BollingerBands', ['upperband', 'middleband', 'lowerband'])


def bollinger_bands(candles: np.ndarray, period: int = 20, devup: float = 2, devdn: float = 2, matype: int = 0,
                    source_type: str = "close",
                    sequential: bool = False) -> BollingerBands:
    """
    BBANDS - Bollinger Bands

    :param candles: np.ndarray
    :param period: int - default: 20
    :param devup: float - default: 2
    :param devdn: float - default: 2
    :param matype: int - default: 0
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: BollingerBands(upperband, middleband, lowerband)
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    upperbands, middlebands, lowerbands = talib.BBANDS(source, timeperiod=period, nbdevup=devup, nbdevdn=devdn,
                                                       matype=matype)

    if sequential:
        return BollingerBands(upperbands, middlebands, lowerbands)
    else:
        return BollingerBands(upperbands[-1], middlebands[-1], lowerbands[-1])
