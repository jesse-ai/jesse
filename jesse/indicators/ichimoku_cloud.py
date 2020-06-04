from collections import namedtuple

import numpy as np

IchimokuCloud = namedtuple('IchimokuCloud', ['conversion_line', 'base_line', 'span_a', 'span_b'])


def ichimoku_cloud(candles: np.ndarray, conversion_line_period=9, base_line_period=26, lagging_line_period=52,
                   displacement=26) -> IchimokuCloud:
    """
    Ichimoku Cloud

    :param candles: np.ndarray
    :param conversion_line_period: int - default=9
    :param base_line_period: int - default=26
    :param lagging_line_period: int - default=52
    :param displacement: - default=26

    :return: IchimokuCloud(conversion_line, base_line, span_a, span_b)
    """
    if len(candles) < 80:
        return IchimokuCloud(np.nan, np.nan, np.nan, np.nan)

    if len(candles) > 80:
        candles = candles[-80:]

    # earlier
    arr = candles[:-(displacement - 1)]

    small_period = arr[-conversion_line_period:]
    mid_period = arr[-base_line_period:]
    long_period = arr[-lagging_line_period:]

    small_ph = small_period[:, 3].max()
    small_pl = small_period[:, 4].min()
    mid_ph = mid_period[:, 3].max()
    mid_pl = mid_period[:, 4].min()
    long_ph = long_period[:, 3].max()
    long_pl = long_period[:, 4].min()

    early_conversion_line = (small_ph + small_pl) / 2
    early_base_line = (mid_ph + mid_pl) / 2
    span_a = (early_conversion_line + early_base_line) / 2
    span_b = (long_ph + long_pl) / 2

    # current
    arr = candles
    small_period = arr[-conversion_line_period:]
    mid_period = arr[-base_line_period:]

    small_ph = small_period[:, 3].max()
    small_pl = small_period[:, 4].min()
    mid_ph = mid_period[:, 3].max()
    mid_pl = mid_period[:, 4].min()

    current_conversion_line = (small_ph + small_pl) / 2
    current_base_line = (mid_ph + mid_pl) / 2

    return IchimokuCloud(current_conversion_line, current_base_line, span_a, span_b)
