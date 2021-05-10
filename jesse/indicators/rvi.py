from typing import Union

import numpy as np
import talib
from jesse.indicators.ma import ma

from jesse.helpers import get_candle_source, same_length
from jesse.helpers import slice_candles
from jesse.indicators.mean_ad import mean_ad
from jesse.indicators.median_ad import median_ad

def rvi(candles: np.ndarray, period: int = 10, ma_len: int = 14, matype: int = 1, devtype: int = 0, source_type: str = "close",
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
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)

    if devtype == 0:
      dev = talib.STDDEV(source, period)
    elif devtype == 1:
      dev = mean_ad(source, period, sequential=True)
    elif devtype == 2:
      dev = median_ad(source, period, sequential=True)

    diff = np.diff(source)
    diff = same_length(source, diff)

    up = np.nan_to_num(np.where(diff <= 0, 0, dev))
    down = np.nan_to_num(np.where(diff > 0, 0, dev))

    up_avg = ma(up, period=ma_len, matype=matype, sequential=True)
    down_avg = ma(down, period=ma_len, matype=matype, sequential=True)

    result = 100 * (up_avg / (up_avg + down_avg))

    return result if sequential else result[-1]
