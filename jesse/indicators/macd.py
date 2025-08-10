from collections import namedtuple
import numpy as np
from jesse.helpers import get_candle_source, slice_candles
from jesse_rust import macd as macd_rust

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

    if source.size == 0:
        return MACD(np.nan, np.nan, np.nan) if not sequential else MACD(np.array([]), np.array([]), np.array([]))

    macd_line, signal_line, hist = macd_rust(source, fast_period, slow_period, signal_period)

    if sequential:
        return MACD(macd_line, signal_line, hist)
    else:
        return MACD(macd_line[-1], signal_line[-1], hist[-1])
