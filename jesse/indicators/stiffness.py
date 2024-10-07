from collections import namedtuple

from .sma import sma
from .ema import ema
from .stddev import stddev

import numpy as np

from jesse.helpers import get_candle_source, slice_candles


def stiffness(candles: np.ndarray, ma_length: int = 100, stiff_length: int = 60, stiff_smooth: int = 3, source_type: str = "close") -> float:
    """
    @author daviddtech
    credits: https://www.tradingview.com/script/MOw6mUQl-Stiffness-Indicator-DaviddTech

    STIFNESS - Stifness

    :param candles: np.ndarray
    :param ma_length: int - default: 100
    :param stiff_length: int - default: 60
    :param stiff_smooth: int - default: 3
    :param source_type: str - default: "close"

    :return: Stiffness(stiffness, threshold)
    """
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, False)
        source = get_candle_source(candles, source_type=source_type)

    bound_stiffness = sma(source, ma_length, sequential=True) - 0.2 * \
        stddev(source, ma_length, sequential=True)
    sum_above_stiffness = _count_price_exceed_series(source, bound_stiffness, stiff_length)
    return ema(np.array(sum_above_stiffness) * 100 / stiff_length, period=stiff_smooth)


def _count_price_exceed_series(close_prices, art_series, length):
    ex_counts = []

    for i in range(len(close_prices)):
        if i < length:
            ex_counts.append(0)
            continue
        count = 0

        for j in range(i - length + 1, i + 1):
            if close_prices[j] > art_series[j]:
                count += 1

        ex_counts.append(count)

    return ex_counts
