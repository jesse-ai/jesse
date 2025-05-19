from collections import namedtuple

import numpy as np
from numba import njit

from jesse.helpers import get_candle_source, same_length, slice_candles

StochasticRSI = namedtuple('StochasticRSI', ['k', 'd'])


@njit(cache=True)
def _rolling_window(a, window):
    """Helper function to create rolling windows of data"""
    shape = a.shape[:-1] + (a.shape[-1] - window + 1, window)
    strides = a.strides + (a.strides[-1],)
    return np.lib.stride_tricks.as_strided(a, shape=shape, strides=strides)


@njit(cache=True)
def _calculate_stoch(data, period_stoch, k_period, d_period):
    """Calculate stochastic oscillator values"""
    # Calculate rolling min and max
    rolling_mins = np.array([np.min(w) for w in _rolling_window(data, period_stoch)])
    rolling_maxs = np.array([np.max(w) for w in _rolling_window(data, period_stoch)])

    # Calculate %K
    k_fast = 100 * (data[period_stoch-1:] - rolling_mins) / (rolling_maxs - rolling_mins)

    # Calculate smoothed %K (which becomes the final %K)
    k = np.zeros_like(k_fast)
    for i in range(k_period-1, len(k_fast)):
        k[i] = np.mean(k_fast[i-k_period+1:i+1])

    # Calculate %D (SMA of %K)
    d = np.zeros_like(k)
    for i in range(d_period-1, len(k)):
        d[i] = np.mean(k[i-d_period+1:i+1])

    return k, d


@njit(cache=True)
def _calculate_rsi(source, period):
    n = len(source)
    rsi = np.full(n, np.nan)  # initialize all values as NaN
    if n <= period:
        return rsi

    # Vectorized computation of price differences
    delta = source[1:] - source[:-1]

    # Compute ups and downs using numpy where
    ups = np.where(delta > 0, delta, 0.0)
    downs = np.where(delta < 0, -delta, 0.0)

    # Initial average gain and loss
    avg_gain = np.mean(ups[:period])
    avg_loss = np.mean(downs[:period])

    # First RSI value at index 'period'
    if avg_loss == 0:
        rsi[period] = 100.0
    else:
        rsi[period] = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)

    # Recursive calculation for subsequent RSI values
    for i in range(period, len(ups)):
        avg_gain = (avg_gain * (period - 1) + ups[i]) / period
        avg_loss = (avg_loss * (period - 1) + downs[i]) / period
        if avg_loss == 0:
            rsi[i + 1] = 100.0
        else:
            rsi[i + 1] = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    
    return rsi


def srsi(candles: np.ndarray, period: int = 14, period_stoch: int = 14, k: int = 3, d: int = 3,
         source_type: str = "close", sequential: bool = False) -> StochasticRSI:
    """
    Stochastic RSI

    :param candles: np.ndarray
    :param period: int - default: 14 - RSI Length
    :param period_stoch: int - default: 14 - Stochastic Length
    :param k: int - default: 3
    :param d: int - default: 3
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: StochasticRSI(k, d)
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    rsi_np = _calculate_rsi(source, period)
    rsi_np = rsi_np[np.logical_not(np.isnan(rsi_np))]

    # Calculate stochastic values
    fast_k, fast_d = _calculate_stoch(rsi_np, period_stoch, k, d)

    if sequential:
        # Pad the beginning with NaN to match the original length
        pad_length = len(candles) - len(fast_k)
        fast_k = np.concatenate((np.full(pad_length, np.nan), fast_k))
        fast_d = np.concatenate((np.full(pad_length, np.nan), fast_d))
        return StochasticRSI(fast_k, fast_d)
    else:
        return StochasticRSI(fast_k[-1], fast_d[-1])
