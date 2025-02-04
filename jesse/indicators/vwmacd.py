from collections import namedtuple

import numpy as np
from .vwma import vwma

from jesse.helpers import slice_candles

VWMACD = namedtuple('VWMACD', ['macd', 'signal', 'hist'])


def vwmacd(candles: np.ndarray, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9,
           sequential: bool = False) -> VWMACD:
    """
    @author David.
    credits: https://www.tradingview.com/script/33Y1LzRq-Volume-Weighted-Moving-Average-Convergence-Divergence-MACD/
    VWMACD - Volume Weighted Moving Average Convergence/Divergence

    :param candles: np.ndarray
    :param fast_period: int - default: 12
    :param slow_period: int - default: 26
    :param signal_period: int - default: 9
    :param sequential: bool - default: False

    :return: VWMACD(macd, signal, hist)
    """
    fastWMA = vwma(candles, fast_period, sequential=True)
    slowWMA = vwma(candles, slow_period, sequential=True)

    macd_val = fastWMA - slowWMA
    signal = vwma(macd_val, signal_period, sequential=True)
    hist = macd_val - signal

    if sequential:
        return VWMACD(macd_val, signal, hist)
    else:
        return VWMACD(macd_val[-1], signal[-1], hist[-1])
