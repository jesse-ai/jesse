from collections import namedtuple

import numpy as np
from numba import njit

from jesse.helpers import slice_candles

SuperTrend = namedtuple('SuperTrend', ['trend', 'changed'])


def supertrend(candles: np.ndarray, period: int = 10, factor: float = 3, sequential: bool = False) -> SuperTrend:
    """
    SuperTrend
    :param candles: np.ndarray
    :param period: int - default=14
    :param factor: float - default=3
    :param sequential: bool - default=False
    :return: SuperTrend(trend, changed)
    """

    candles = slice_candles(candles, sequential)

    atr = atr_np(candles[:, 3], candles[:, 4], candles[:, 2], period)

    super_trend, changed = supertrend_fast(candles, atr, factor, period)

    if sequential:
        return SuperTrend(super_trend, changed)
    else:
        return SuperTrend(super_trend[-1], changed[-1])


def atr_np(high, low, close, period):
    # Compute true range
    n = len(close)
    tr = np.empty(n, dtype=np.float64)
    tr[0] = high[0] - low[0]
    if n > 1:
        diff1 = high[1:] - low[1:]
        diff2 = np.abs(high[1:] - close[:-1])
        diff3 = np.abs(low[1:] - close[:-1])
        tr[1:] = np.maximum(np.maximum(diff1, diff2), diff3)

    # Initialize ATR array; first period-1 values set to nan
    atr = np.empty(n, dtype=np.float64)
    atr[:period-1] = np.nan
    if n >= period:
        init = np.mean(tr[:period])
        atr[period-1] = init
        alpha = 1.0 / period
        L = n - period
        if L > 0:
            # Create lower-triangular weights matrix where each row i contains weights (1 - alpha)^(i - j) for j=0..i
            weights = np.tril(np.power(1 - alpha, np.subtract.outer(np.arange(L), np.arange(L))))
            # Compute the weighted sum for TR values from index period to n-1
            weighted_sum = alpha * (weights @ tr[period:])
            # Compute the offset from the initial ATR
            offset = init * np.power(1 - alpha, np.arange(1, L+1))
            atr[period:] = offset + weighted_sum
    return atr


@njit(cache=True)
def supertrend_fast(candles, atr, factor, period):
    # Calculation of SuperTrend
    upper_basic = (candles[:, 3] + candles[:, 4]) / 2 + (factor * atr)
    lower_basic = (candles[:, 3] + candles[:, 4]) / 2 - (factor * atr)
    upper_band = upper_basic.copy()
    lower_band = lower_basic.copy()
    super_trend = np.zeros(len(candles))
    changed = np.zeros(len(candles))

    # calculate the bands:
    # in an UPTREND, lower band does not decrease
    # in a DOWNTREND, upper band does not increase
    for i in range(period, len(candles)):
        # if currently in DOWNTREND (i.e. price is below upper band)
        prevClose = candles[i - 1, 2]
        prevUpperBand = upper_band[i - 1]
        currUpperBasic = upper_basic[i]
        if prevClose <= prevUpperBand:
            # upper band will DECREASE in value only
            upper_band[i] = min(currUpperBasic, prevUpperBand)

        # if currently in UPTREND (i.e. price is above lower band)
        prevLowerBand = lower_band[i - 1]
        currLowerBasic = lower_basic[i]
        if prevClose >= prevLowerBand:
            # lower band will INCREASE in value only
            lower_band[i] = max(currLowerBasic, prevLowerBand)

        # >>>>>>>> previous period SuperTrend <<<<<<<<
        if prevClose <= prevUpperBand:
            super_trend[i - 1] = prevUpperBand
        else:
            super_trend[i - 1] = prevLowerBand
        prevSuperTrend = super_trend[i - 1]

    for i in range(period, len(candles)):
        prevClose = candles[i - 1, 2]
        prevUpperBand = upper_band[i - 1]
        currUpperBand = upper_band[i]
        prevLowerBand = lower_band[i - 1]
        currLowerBand = lower_band[i]
        prevSuperTrend = super_trend[i - 1]

        # >>>>>>>>> current period SuperTrend <<<<<<<<<
        if prevSuperTrend == prevUpperBand:  # if currently in DOWNTREND
            if candles[i, 2] <= currUpperBand:
                super_trend[i] = currUpperBand
                changed[i] = False
            else:
                super_trend[i] = currLowerBand
                changed[i] = True
        elif prevSuperTrend == prevLowerBand:  # if currently in UPTREND
            if candles[i, 2] >= currLowerBand:
                super_trend[i] = currLowerBand
                changed[i] = False
            else:
                super_trend[i] = currUpperBand
                changed[i] = True
    return super_trend, changed
