from collections import namedtuple

import numpy as np

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
    if len(volume_data) < period:
        volume_ma = np.full(len(volume_data), np.nan)
    else:
        volume_ma = np.concatenate((np.full(period - 1, np.nan), np.convolve(volume_data, np.ones(period) / period, mode='valid')))

    if sequential:
        return Volume(volume_data, volume_ma)
    else:
        return Volume(volume_data[-1], volume_ma[-1])
