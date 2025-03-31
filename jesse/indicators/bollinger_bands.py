from collections import namedtuple

import numpy as np
from numba import njit

from jesse.helpers import get_candle_source, slice_candles
from jesse.indicators.ma import ma
from jesse.indicators.mean_ad import mean_ad
from jesse.indicators.median_ad import median_ad

BollingerBands = namedtuple('BollingerBands', ['upperband', 'middleband', 'lowerband'])


@njit
def _moving_std_numba(source, period):
    n = len(source)
    result = np.empty(n, dtype=np.float64)
    # Fill the first period-1 entries with NaN
    for i in range(period - 1):
        result[i] = np.nan
    # Calculate standard deviation for each window of 'period' elements
    for i in range(period - 1, n):
        sum_val = 0.0
        sum_sq = 0.0
        for j in range(i - period + 1, i + 1):
            x = source[j]
            sum_val += x
            sum_sq += x * x
        mean = sum_val / period
        variance = sum_sq / period - mean * mean
        # Guard against possible negative variance from precision issues
        if variance < 0.0:
            variance = 0.0
        result[i] = variance ** 0.5
    return result


def moving_std(source, period):
    # Use the Numba-accelerated function instead of the Python loop with np.std
    return _moving_std_numba(source, period)


def bollinger_bands(
        candles: np.ndarray,
        period: int = 20,
        devup: float = 2,
        devdn: float = 2,
        matype: int = 0,
        devtype: int = 0,
        source_type: str = "close",
        sequential: bool = False
) -> BollingerBands:
    """
    BBANDS - Bollinger Bands

    :param candles: np.ndarray
    :param period: int - default: 20
    :param devup: float - default: 2
    :param devdn: float - default: 2
    :param matype: int - default: 0
    :param devtype: int - default: 0
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: BollingerBands(upperband, middleband, lowerband)
    """
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    if devtype == 0:
        dev = moving_std(source, period)
    elif devtype == 1:
        dev = mean_ad(source, period, sequential=True)
    elif devtype == 2:
        dev = median_ad(source, period, sequential=True)
    else:
        raise ValueError("devtype not in (0, 1, 2)")

    if matype == 24 or matype == 29:
        middlebands = ma(candles, period=period, matype=matype, source_type=source_type, sequential=True)
    else:
        middlebands = ma(source, period=period, matype=matype, sequential=True)
    upperbands = middlebands + devup * dev
    lowerbands = middlebands - devdn * dev

    if sequential:
        return BollingerBands(upperbands, middlebands, lowerbands)
    else:
        return BollingerBands(upperbands[-1], middlebands[-1], lowerbands[-1])
