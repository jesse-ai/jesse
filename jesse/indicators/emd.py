from collections import namedtuple

import numpy as np
import talib
from numba import njit

from jesse.helpers import get_config

EMD = namedtuple('EMD', ['upperband', 'middleband', 'lowerband'])


def emd(candles: np.ndarray, period: int = 20, delta=0.5, fraction=0.1, sequential: bool = False) -> EMD:
    """
    Empirical Mode Decomposition by John F. Ehlers and Ric Way

    :param candles: np.ndarray
    :param period: int - default=20
    :param delta: float - default=0.5
    :param fraction: float - default=0.1
    :param sequential: bool - default=False

    :return: EMD(upperband, middleband, lowerband)
    """
    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

    price = (candles[:, 3] + candles[:, 4]) / 2

    bp = bp_fast(price, period, delta)

    mean = talib.SMA(bp, timeperiod=2 * period)
    peak, valley = peak_valley_fast(bp, price)

    avg_peak = fraction * talib.SMA(peak, timeperiod=50)
    avg_valley = fraction * talib.SMA(valley, timeperiod=50)

    if sequential:
        return EMD(avg_peak, mean, avg_valley)
    else:
        return EMD(avg_peak[-1], mean[-1], avg_valley[-1])


@njit
def bp_fast(price, period, delta):
    # bandpass filter
    beta = np.cos(2 * np.pi / period)
    gamma = 1 / np.cos(4 * np.pi * delta / period)
    alpha = gamma - np.sqrt(gamma * gamma - 1)
    bp = np.zeros_like(price)

    for i in range(price.shape[0]):
        if i > 2:
            bp[i] = 0.5 * (1 - alpha) * (price[i] - price[i - 2]) + beta * (1 + alpha) * bp[i - 1] - alpha * bp[i - 2]
        else:
            bp[i] = 0.5 * (1 - alpha) * (price[i] - price[i - 2])
    return bp


@njit
def peak_valley_fast(bp, price):
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

    return peak, valley
