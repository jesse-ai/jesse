import math
from collections import namedtuple

import numpy as np
import talib

EMD = namedtuple('EMD', ['upperband', 'middleband', 'lowerband'])


def emd(candles: np.ndarray, period=20, delta=0.5, fraction=0.1, sequential=False) -> EMD:
    """
    Empirical Mode Decomposition by John F. Ehlers and Ric Way

    :param candles: np.ndarray
    :param period: int - default=20
    :param delta: float - default=0.5
    :param fraction: float - default=0.1
    :param sequential: bool - default=False

    :return: EMD(upperband, middleband, lowerband)
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    price = (candles[:, 3] + candles[:, 4]) / 2
    # bandpass filter
    beta = math.cos(2 * math.pi / period)
    gamma = 1 / math.cos(4 * math.pi * delta / period)
    alpha = gamma - math.sqrt(gamma * gamma - 1)
    bp = np.zeros_like(price)

    for i in range(price.shape[0]):
        if i > 2:
            bp[i] = 0.5 * (1 - alpha) * (price[i] - price[i - 2]) + beta * (1 + alpha) * bp[i - 1] - alpha * bp[i - 2]
        else:
            bp[i] = 0.5 * (1 - alpha) * (price[i] - price[i - 2])

    mean = talib.SMA(bp, timeperiod=2 * period)

    peak = np.copy(bp)
    valley = np.copy(bp)

    for i in range(price.shape[0]):
        peak[i] = peak[i - 1]
        valley[i] = valley[i - 1]
        if i > 2:
            if bp[i - 1] > bp[i] and bp[i - 1] > bp[i - 2]:
                peak[i] = bp[i - 1]
            if bp[i - 1] < bp[i] and bp[i - 1] < bp[i - 2]:
                valley[i] = bp[i - 1]

    avg_peak = fraction * talib.SMA(peak, timeperiod=50)
    avg_valley = fraction * talib.SMA(valley, timeperiod=50)

    if sequential:
        return EMD(avg_peak, mean, avg_valley)
    else:
        return EMD(avg_peak[-1], mean[-1], avg_valley[-1])
