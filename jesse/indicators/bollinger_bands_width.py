from typing import Union

import numpy as np
import talib

from jesse.helpers import get_candle_source


def bollinger_bands_width(candles: np.ndarray, period=20, devup=2, devdn=2, matype=0, source_type="close",
                          sequential=False) -> Union[float, np.ndarray]:
    """
    BBW - Bollinger Bands Width - Bollinger Bands Bandwidth

    :param candles: np.ndarray
    :param period: int - default: 20
    :param devup: float - default: 2
    :param devdn: float - default: 2
    :param matype: int - default: 0
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)
    upperbands, middlebands, lowerbands = talib.BBANDS(source, timeperiod=period, nbdevup=devup, nbdevdn=devdn,
                                                       matype=matype)

    if sequential:
        return (upperbands - lowerbands) / middlebands
    else:
        return (upperbands[-1] - lowerbands[-1]) / middlebands[-1]
