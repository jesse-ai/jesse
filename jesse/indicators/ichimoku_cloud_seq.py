from collections import namedtuple

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from jesse.helpers import np_shift, slice_candles

IchimokuCloud = namedtuple('IchimokuCloud',
                           ['conversion_line', 'base_line', 'span_a', 'span_b', 'lagging_line', 'future_span_a',
                            'future_span_b'])


def ichimoku_cloud_seq(candles: np.ndarray, conversion_line_period: int = 9, base_line_period: int = 26,
                       lagging_line_period: int = 52, displacement: int = 26,
                       sequential: bool = False) -> IchimokuCloud:
    """
    Ichimoku Cloud

    :param candles: np.ndarray
    :param conversion_line_period: int - default: 9
    :param base_line_period: int - default: 26
    :param lagging_line_period: int - default: 52
    :param displacement: - default: 26
    :param sequential: bool - default: False

    :return: IchimokuCloud
    """

    if candles.shape[0] < lagging_line_period + displacement:
        raise ValueError("Too few candles available for lagging_line_period + displacement.")

    candles = slice_candles(candles, sequential)

    conversion_line = _line_helper(candles, conversion_line_period)
    base_line = _line_helper(candles, base_line_period)
    span_b_pre = _line_helper(candles, lagging_line_period)
    span_b = np_shift(span_b_pre, displacement, fill_value=np.nan)
    span_a_pre = (conversion_line + base_line) / 2
    span_a = np_shift(span_a_pre, displacement, fill_value=np.nan)
    lagging_line = np_shift(candles[:, 2], displacement - 1, fill_value=np.nan)

    if sequential:
        return IchimokuCloud(conversion_line, base_line, span_a, span_b, lagging_line, span_a_pre, span_b_pre)
    else:
        return IchimokuCloud(conversion_line[-1], base_line[-1], span_a[-1], span_b[-1], lagging_line[-1],
                             span_a_pre[-1], span_b_pre[-1])

def _line_helper(candles, period):
    small_ph = _rolling_max(candles[:, 3], period)
    small_pl = _rolling_min(candles[:, 4], period)
    return (small_ph + small_pl) / 2

def _rolling_max(a, period):
    n = len(a)
    if n < period:
        return np.full(n, np.nan)
    windows = sliding_window_view(a, window_shape=period)
    r = np.empty(n, dtype=a.dtype)
    r[:period-1] = np.nan
    r[period-1:] = np.max(windows, axis=-1)
    return r

def _rolling_min(a, period):
    n = len(a)
    if n < period:
        return np.full(n, np.nan)
    windows = sliding_window_view(a, window_shape=period)
    r = np.empty(n, dtype=a.dtype)
    r[:period-1] = np.nan
    r[period-1:] = np.min(windows, axis=-1)
    return r
