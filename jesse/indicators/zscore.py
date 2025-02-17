from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, slice_candles
from jesse.indicators.ma import ma
from jesse.indicators.mean_ad import mean_ad
from jesse.indicators.median_ad import median_ad


def zscore(candles: np.ndarray, period: int = 14, matype: int = 0, nbdev: float = 1, devtype: int = 0, source_type: str = "close",
           sequential: bool = False) -> Union[float, np.ndarray]:
    """
    zScore

    :param candles: np.ndarray
    :param period: int - default: 14
    :param matype: int - default: 0
    :param nbdev: float - default: 1
    :param devtype: int - default: 0
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    if matype == 24 or matype == 29:
        means = ma(candles, period=period, matype=matype, source_type=source_type, sequential=True)
    else:
        means = ma(source, period=period, matype=matype, sequential=True)

    if devtype == 0:
        if len(source) < period:
            sigmas = np.full_like(source, np.nan, dtype=np.float64)
        else:
            # Create a sliding window view of the source array
            rolling_windows = np.lib.stride_tricks.sliding_window_view(source, window_shape=period)
            # Calculate std using population formula (ddof=0)
            std_values = np.std(rolling_windows, axis=1, ddof=0)
            sigmas = np.full(source.shape, np.nan, dtype=np.float64)
            sigmas[period-1:] = std_values
        sigmas = sigmas * nbdev
    elif devtype == 1:
       sigmas = mean_ad(source, period, sequential=True) * nbdev
    elif devtype == 2:
       sigmas = median_ad(source, period, sequential=True) * nbdev

    zScores = (source - means) / sigmas

    return zScores if sequential else zScores[-1]
