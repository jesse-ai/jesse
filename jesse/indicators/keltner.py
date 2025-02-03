from collections import namedtuple

import numpy as np

from jesse.helpers import get_candle_source, slice_candles
from jesse.indicators.ma import ma

KeltnerChannel = namedtuple('KeltnerChannel', ['upperband', 'middleband', 'lowerband'])


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    tr = np.empty_like(high)
    tr[0] = high[0] - low[0]
    # Compute true range for the rest of the candles using vectorized operations
    tr[1:] = np.maximum(
        np.maximum(high[1:] - low[1:], np.abs(high[1:] - close[:-1])),
        np.abs(low[1:] - close[:-1])
    )

    atr_vals = np.empty_like(tr, dtype=float)
    # Not enough data for ATR in the first period-1 candles
    atr_vals[:period-1] = float('nan')
    # The first ATR value is a simple average
    atr_vals[period-1] = np.mean(tr[:period])

    # Wilder's smoothing method for subsequent values using vectorized operation with lfilter
    if len(tr) > period:
        alpha = 1 / period
        from scipy.signal import lfilter
        A0 = atr_vals[period - 1]  # initial ATR from simple average
        x = tr[period:]
        # Set the initial condition such that y[0] = (1 - alpha)*A0 + alpha*tr[period]
        zi = [(1 - alpha) * A0]
        y, _ = lfilter([alpha], [1, -(1 - alpha)], x, zi=zi)
        atr_vals[period:] = y
    return atr_vals


def keltner(candles: np.ndarray, period: int = 20, multiplier: float = 2, matype: int = 1, source_type: str = "close",
            sequential: bool = False) -> KeltnerChannel:
    """
    Keltner Channels

    :param candles: np.ndarray
    :param period: int - default: 20
    :param multiplier: float - default: 2
    :param matype: int - default: 1
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: KeltnerChannel(upperband, middleband, lowerband)
    """

    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    e = ma(source, period=period, matype=matype, sequential=True)
    a = _atr(candles[:, 3], candles[:, 4], candles[:, 2], period)

    up = e + a * multiplier
    mid = e
    low = e - a * multiplier

    if sequential:
        return KeltnerChannel(up, mid, low)
    else:
        return KeltnerChannel(up[-1], mid[-1], low[-1])
