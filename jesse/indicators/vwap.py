from typing import Union

import numpy as np
from numpy_groupies import aggregate_nb as aggregate

from jesse.helpers import get_candle_source, slice_candles


def vwap(candles: np.ndarray, source_type: str = "hlc3", anchor: str = "D", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    VWAP

    :param candles: np.ndarray
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)

    group_idx = candles[:, 0].astype('datetime64[ms]').astype(f'datetime64[{anchor}]').astype('int')
    vwap = aggregate(group_idx, candles[:, 5] * source, func='cumsum')
    vwap /= aggregate(group_idx, candles[:, 5], func='cumsum')

    if sequential:
        return vwap
    else:
        return None if np.isnan(vwap[-1]) else vwap[-1]
