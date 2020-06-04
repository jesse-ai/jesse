from collections import namedtuple

import numpy as np

PIVOT = namedtuple('PIVOT', ['r4', 'r3', 'r2', 'r1', 'pp', 's1', 's2', 's3', 's4'])


def pivot(candles: np.ndarray, mode=0, sequential=False) -> PIVOT:
    """
    Pivot Points

    :param candles: np.ndarray
    :param mode: int - default = 0
    :param sequential: bool - default=False

    :return: PIVOT(r4, r3, r2, r1, pp, s1, s2, s3, s4)
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    high = candles[:, 3]
    low = candles[:, 4]
    close = candles[:, 2]
    open = candles[:, 1]

    s1 = np.full_like(close, np.nan)
    s2 = np.copy(s1)
    s3 = np.copy(s1)
    s4 = np.copy(s1)
    p = np.copy(s1)
    r1 = np.copy(s1)
    r2 = np.copy(s1)
    r3 = np.copy(s1)
    r4 = np.copy(s1)

    # Standard Pivot Points / Floor Pivot Points
    if (mode == 0):
        p = (high + low + close) / 3
        s1 = (2 * p) - high
        s2 = p - (high - low)
        r1 = (2 * p) - low
        r2 = p + (high - low)
    # Fibonacci Pivot Points
    elif (mode == 1):
        p = (high + low + close) / 3
        s1 = p - 0.382 * (high - low)
        s2 = p - 0.618 * (high - low)
        s3 = p - 1 * (high - low)
        r1 = p + 0.382 * (high - low)
        r2 = p + 0.618 * (high - low)
        r3 = p + 1 * (high - low)
    # Demark Pivot Points
    elif (mode == 2):
        p = np.where(close < open, (high + 2 * low + close) / 4, np.where(close > open, (2 * high + low + close) / 4,
                                                                          np.where(close == open,
                                                                                   (high + low + 2 * close) / 4,
                                                                                   np.nan)))
        s1 = np.where(close < open, (high + 2 * low + close) / 2 - high,
                      np.where(close > open, (2 * high + low + close) / 2 - high,
                               np.where(close == open, (high + low + 2 * close) / 2 - high, np.nan)))
        r1 = np.where(close < open, (high + 2 * low + close) / 2 - low,
                      np.where(close > open, (2 * high + low + close) / 2 - low,
                               np.where(close == open, (high + low + 2 * close) / 2 - low, np.nan)))
    elif (mode == 3):
        # Camarilla Pivot Points
        p = (high + low + close) / 3
        r4 = (0.55 * (high - low)) + close
        r3 = (0.275 * (high - low)) + close
        r2 = (0.183 * (high - low)) + close
        r1 = (0.0916 * (high - low)) + close
        s1 = close - (0.0916 * (high - low))
        s2 = close - (0.183 * (high - low))
        s3 = close - (0.275 * (high - low))
        s4 = close - (0.55 * (high - low))
    # Woodie's Pivot Points
    elif (mode == 4):
        p = (high + low + (2 * open)) / 4
        r3 = high + 2 * (p - low)
        r4 = r3 + (high - low)
        r2 = p + (high - low)
        r1 = (2 * p) - low
        s1 = (2 * p) - high
        s2 = p - (high - low)
        s3 = low - 2 * (high - p)
        s4 = s3 - (high - low)

    if sequential:
        return PIVOT(r4, r3, r2, r1, p, s1, s2, s3, s4)
    else:
        return PIVOT(r4[-1], r3[-1], r2[-1], r1[-1], p[-1], s1[-1], s2[-1], s3[-1], s4[-1])
