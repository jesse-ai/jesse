from collections import namedtuple

import numpy as np

from jesse.helpers import get_candle_source, slice_candles
from jesse.indicators.rsi import rsi
from jesse.indicators.sma import sma

StochasticRSI = namedtuple('StochasticRSI', ['k', 'd'])


def srsi(candles: np.ndarray, period: int = 14, period_stoch: int = 14, k: int = 3, d: int = 3,
         source_type: str = "close", sequential: bool = False) -> StochasticRSI:
    """
    Stochastic RSI (pure numpy implementation to ensure test parity)
    """
    candles = slice_candles(candles, sequential)
    source = get_candle_source(candles, source_type=source_type)
    
    # Calculate RSI values (sequential)
    rsi_values = rsi(candles, period=period, source_type=source_type, sequential=True)

    rsi_values = np.asarray(rsi_values, dtype=np.float64)
    n = len(rsi_values)

    # Prepare arrays
    stoch_rsi = np.full(n, np.nan)

    # Rolling min/max of RSI
    for i in range(period_stoch - 1, n):
        window = rsi_values[i + 1 - period_stoch: i + 1]
        min_rsi = np.nanmin(window)
        max_rsi = np.nanmax(window)
        if max_rsi - min_rsi != 0:
            stoch_rsi[i] = 100 * (rsi_values[i] - min_rsi) / (max_rsi - min_rsi)

    # %K and %D via SMA
    k_line = sma(stoch_rsi, k, sequential=True)
    d_line = sma(k_line, d, sequential=True)

    if sequential:
        return StochasticRSI(k_line, d_line)
    else:
        return StochasticRSI(k_line[-1], d_line[-1])
