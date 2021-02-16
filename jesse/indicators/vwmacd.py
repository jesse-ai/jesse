from collections import namedtuple

import numpy as np
import talib

from jesse.helpers import get_config

VWMACD = namedtuple('VWMACD', ['macd', 'signal', 'hist'])


def vwmacd(candles: np.ndarray, fast_period: int = 12, slow_period: int = 26, signalperiod: int = 9,
           sequential: bool = False) -> VWMACD:
    """
    VWMACD - Volume Weighted Moving Average Convergence/Divergence

    :param candles: np.ndarray
    :param fast_period: int - default: 12
    :param slow_period: int - default: 26
    :param signal_period: int - default: 9
    :param sequential: bool - default: False

    :return: VWMACD(macd, signal, hist)
    """
    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

    vwma_slow = talib.SMA(candles[:, 2] * candles[:, 5], slow_period) / talib.SMA(candles[:, 5], slow_period)
    vwma_fast = talib.SMA(candles[:, 2] * candles[:, 5], fast_period) / talib.SMA(candles[:, 5], fast_period)
    vwmacd = vwma_fast - vwma_slow
    signal = talib.EMA(vwmacd, signalperiod)
    hist = vwmacd - signal

    if sequential:
        return VWMACD(vwmacd, signal, hist)
    else:
        return VWMACD(vwmacd[-1], signal[-1], hist[-1])
