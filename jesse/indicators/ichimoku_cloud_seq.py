from collections import namedtuple

import numpy as np
import talib

from jesse.helpers import get_config
from jesse.helpers import np_shift

IchimokuCloud = namedtuple('IchimokuCloud',
                           ['conversion_line', 'base_line', 'span_a', 'span_b', 'lagging_line', 'future_span_a',
                            'future_span_b'])


def ichimoku_cloud_seq(candles: np.ndarray, conversion_line_period: int = 9, base_line_period: int = 26,
                       lagging_line_period: int = 52, displacement: int = 26,
                       sequential: bool = False) -> IchimokuCloud:
    """
    Ichimoku Cloud

    :param candles: np.ndarray
    :param conversion_line_period: int - default=9
    :param base_line_period: int - default=26
    :param lagging_line_period: int - default=52
    :param displacement: - default=26
    :param sequential: bool - default=False

    :return: IchimokuCloud
    """

    if len(candles) < lagging_line_period + displacement:
        raise ValueError("Too few candles available for lagging_line_period + displacement.")

    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

    small_ph = talib.MAX(candles[:, 3], conversion_line_period)
    small_pl = talib.MIN(candles[:, 4], conversion_line_period)
    conversion_line = (small_ph + small_pl) / 2

    mid_ph = talib.MAX(candles[:, 3], base_line_period)
    mid_pl = talib.MIN(candles[:, 4], base_line_period)
    base_line = (mid_ph + mid_pl) / 2

    long_ph = talib.MAX(candles[:, 3], lagging_line_period)
    long_pl = talib.MIN(candles[:, 4], lagging_line_period)
    span_b_pre = (long_ph + long_pl) / 2
    span_b = np_shift(span_b_pre, displacement, fill_value=np.nan)
    span_a_pre = (conversion_line + base_line) / 2
    span_a = np_shift(span_a_pre, displacement, fill_value=np.nan)

    lagging_line = np_shift(candles[:, 2], displacement - 1, fill_value=np.nan)

    if sequential:
        return IchimokuCloud(conversion_line, base_line, span_a, span_b, lagging_line, span_a_pre, span_b_pre)
    else:
        return IchimokuCloud(conversion_line[-1], base_line[-1], span_a[-1], span_b[-1], lagging_line[-1],
                             span_a_pre[-1], span_b_pre[-1])
