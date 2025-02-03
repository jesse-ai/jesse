from collections import namedtuple

import numpy as np
from jesse.indicators import ema
from jesse.helpers import get_candle_source, slice_candles

MACD = namedtuple('MACD', ['macd', 'signal', 'hist'])

def macd(candles: np.ndarray, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9,
         source_type: str = "close",
         sequential: bool = False) -> MACD:
    """
    MACD - Moving Average Convergence/Divergence

    :param candles: np.ndarray
    :param fast_period: int - default: 12
    :param slow_period: int - default: 26
    :param signal_period: int - default: 9
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: MACD(macd, signal, hist)
    """

    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    ema_fast = ema(source, fast_period, sequential=True)
    ema_slow = ema(source, slow_period, sequential=True)
    macd_line = ema_fast - ema_slow
    # Handle NaN values in macd_line before calculating EMA
    macd_line_cleaned = np.nan_to_num(macd_line, nan=0.0)
    signal_line = ema(macd_line_cleaned, signal_period, sequential=True)
    hist = macd_line - signal_line

    if sequential:
        return MACD(macd_line_cleaned, signal_line, hist)
    else:
        return MACD(macd_line_cleaned[-1], signal_line[-1], hist[-1])
