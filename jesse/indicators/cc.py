from typing import Union

import numpy as np
import talib

from jesse.helpers import get_candle_source
from jesse.helpers import get_config


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
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

    source = get_candle_source(candles, source_type=source_type)
    res = talib.WMA(talib.ROC(source, timeperiod=roc_long_period) + talib.ROC(source, timeperiod=roc_short_period),
                    timeperiod=wma_period)

    return res if sequential else res[-1]
