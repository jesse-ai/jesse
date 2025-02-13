from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, slice_candles
from .roc import roc
from .wma import wma


def cc(candles: np.ndarray, wma_period: int = 10, roc_short_period: int = 11, roc_long_period: int = 14,
       source_type: str = "close",
       sequential: bool = False) -> Union[float, np.ndarray]:
    """
    CC - Coppock Curve

    :param candles: np.ndarray
    :param wma_period: int - default: 10
    :param roc_short_period: int - default: 11
    :param roc_long_period: int - default: 14
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)
    roc_long = roc(source, roc_long_period, sequential=True)
    roc_short = roc(source, roc_short_period, sequential=True)
    roc_sum = roc_long + roc_short
    res = wma(roc_sum, wma_period, sequential=True)

    return res if sequential else res[-1]
