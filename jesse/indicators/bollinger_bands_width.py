import numpy as np
import talib

from typing import Union


def bollinger_bands_width(candles: np.ndarray, period=20, sequential=False) -> Union[float, np.ndarray]:
    """
    BBW - Bollinger Bands Width - Bollinger Bands Bandwidth

    :param candles: np.ndarray
    :param period: int - default: 20
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    upperbands, middlebands, lowerbands = talib.BBANDS(candles[:, 2], timeperiod=period, nbdevup=2, nbdevdn=2, matype=0)

    if sequential:
        return (upperbands - lowerbands) / middlebands
    else:
        return (upperbands[-1] - lowerbands[-1]) / middlebands[-1]
