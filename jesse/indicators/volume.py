from collections import namedtuple

import numpy as np
import talib

from jesse.helpers import slice_candles

Volume = namedtuple("Volume", ["volume", "ma"])


def volume(
    candles: np.ndarray,
    period: int = 20,
    sequential: bool = False
) -> Volume:
    """
    Volume with Moving Average

    :param candles: np.ndarray
    :param period: int - default: 20
    :param sequential: bool - default: False

    :return: Volume(volume, ma)
    """
    candles = slice_candles(candles, sequential)

    volume_data = candles[:, 5]
    volume_ma = talib.SMA(volume_data, timeperiod=period)

    if sequential:
        return Volume(volume_data, volume_ma)
    else:
        return Volume(volume_data[-1], volume_ma[-1])
