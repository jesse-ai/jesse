from typing import Union

import numpy as np
import talib

from jesse.helpers import get_candle_source
from jesse.helpers import get_config


def rvi(candles: np.ndarray, period: int = 10, ma_len: int = 14, matype: int = 1, source_type: str = "close",
        sequential: bool = False) -> Union[float, np.ndarray]:
    """
    RVI - Relative Volatility Index
    :param candles: np.ndarray
    :param period: int - default: 10
    :param ma_len: int - default: 14
    :param matype: int - default: 1
    :param source_type: str - default: "close"
    :param sequential: bool - default=False
    :return: float | np.ndarray
    """
    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

    source = get_candle_source(candles, source_type=source_type)

    stdev = talib.STDDEV(source, timeperiod=period)

    diff = np.diff(source)
    diff = np.concatenate((np.full((candles.shape[0] - diff.shape[0]), 0), diff), axis=0)

    up = np.nan_to_num(np.where(diff <= 0, 0, stdev))
    down = np.nan_to_num(np.where(diff > 0, 0, stdev))

    up_avg = talib.MA(up, timeperiod=ma_len, matype=matype)
    down_avg = talib.MA(down, timeperiod=ma_len, matype=matype)

    result = 100 * (up_avg / (up_avg + down_avg))

    return result if sequential else result[-1]
