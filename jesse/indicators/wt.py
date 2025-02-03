from collections import namedtuple

from jesse.helpers import get_candle_source, slice_candles

import numpy as np

Wavetrend = namedtuple('Wavetrend', ['wt1', 'wt2', 'wtCrossUp', 'wtCrossDown', 'wtOversold', 'wtOverbought', 'wtVwap'])


# Wavetrend indicator ported from:  https://www.tradingview.com/script/Msm4SjwI-VuManChu-Cipher-B-Divergences/
#                                   https://www.tradingview.com/script/2KE8wTuF-Indicator-WaveTrend-Oscillator-WT/
#
# buySignal = wtCross and wtCrossUp and wtOversold
# sellSignal = wtCross and wtCrossDown and wtOverbought
#
# See https://github.com/ysdede/lazarus3/blob/partialexit/strategies/lazarus3/__init__.py for working jesse.ai example.


def ema(x: np.ndarray, period: int) -> np.ndarray:
    """Compute Exponential Moving Average (EMA) using a vectorized triangular matrix approach."""
    alpha = 2 / (period + 1)
    n = len(x)
    # Create a matrix of differences using outer subtraction
    diff = np.subtract.outer(np.arange(n), np.arange(n))
    # Compute weights: for each t, weight = alpha * (1-alpha)^(t - i) for i<=t, else 0
    weights = alpha * np.power(1 - alpha, diff)
    weights = np.tril(weights)
    return weights.dot(x)

def sma(x: np.ndarray, period: int) -> np.ndarray:
    """Compute Simple Moving Average (SMA) using cumulative sum for a trailing window."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    ret = np.empty(n, dtype=float)
    if period > 1:
        cumsum = np.cumsum(x)
        ret[:period-1] = cumsum[:period-1] / np.arange(1, period)
        ret[period-1:] = (cumsum[period-1:] - np.r_[0.0, cumsum[:-period]]) / period
    else:
        ret = x
    return ret

def wt(candles: np.ndarray,
       wtchannellen: int = 9,
       wtaveragelen: int = 12,
       wtmalen: int = 3,
       oblevel: int = 53,
       oslevel: int = -53,
       source_type: str = "hlc3",
       sequential: bool = False) -> Wavetrend:
    """
    Wavetrend indicator

    :param candles: np.ndarray
    :param wtchannellen:  int - default: 9
    :param wtaveragelen: int - default: 12
    :param wtmalen: int - default: 3
    :param oblevel: int - default: 53
    :param oslevel: int - default: -53
    :param source_type: str - default: "hlc3"
    :param sequential: bool - default: False

    :return: Wavetrend
    """
    candles = slice_candles(candles, sequential)

    src = get_candle_source(candles, source_type=source_type)

    # wt
    esa = ema(src, wtchannellen)
    de = ema(abs(src - esa), wtchannellen)
    ci = (src - esa) / (0.015 * de)
    wt1 = ema(ci, wtaveragelen)
    wt2 = sma(wt1, wtmalen)

    wtVwap = wt1 - wt2
    wtOversold = wt2 <= oslevel
    wtOverbought = wt2 >= oblevel
    wtCrossUp = wt2 - wt1 <= 0
    wtCrossDown = wt2 - wt1 >= 0

    if sequential:
        return Wavetrend(wt1, wt2, wtCrossUp, wtCrossDown, wtOversold, wtOverbought, wtVwap)
    else:
        return Wavetrend(wt1[-1], wt2[-1], wtCrossUp[-1], wtCrossDown[-1], wtOversold[-1], wtOverbought[-1], wtVwap[-1])
