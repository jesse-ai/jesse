from typing import Union

import numpy as np

from jesse.helpers import get_candle_source


def mcginley_dynamic(candles: np.ndarray, period=10, k=0.6, source_type="close", sequential=False) -> Union[
    float, np.ndarray]:
    """
    McGinley Dynamic

    :param candles: np.ndarray
    :param period: int - default: 10
    :param k: float - default: 0.6
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)

    mg = np.full_like(source, np.nan)
    for i in range(len(source)):
        if i == 0:
            mg[i] = source[i]
        else:
            mg[i] = mg[i - 1] + ((source[i] - mg[i - 1]) / np.max([(k * period * ((source[i] / mg[i - 1]) ** 4)), 1]))

    if sequential:
        return mg
    else:
        return None if np.isnan(mg[-1]) else mg[-1]
