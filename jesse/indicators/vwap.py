from typing import Union

import numpy as np
try:
    from numba import njit
    from numpy_groupies import aggregate_nb as aggregate
except ImportError:
    from numpy_groupies import aggregate

from jesse.helpers import get_candle_source, slice_candles


def vwap(
        candles: np.ndarray, source_type: str = "hlc3", anchor: str = "D", sequential: bool = False
) -> Union[float, np.ndarray]:
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
    vwap_values = aggregate(group_idx, candles[:, 5] * source, func='cumsum')
    vwap_values /= aggregate(group_idx, candles[:, 5], func='cumsum')

    if sequential:
        return vwap_values
    else:
        return None if np.isnan(vwap_values[-1]) else vwap_values[-1]
