from typing import Union

import numpy as np
import talib

from jesse.helpers import get_candle_source
from jesse.helpers import get_config
from jesse.indicators import stddev


def rvi(candles: np.ndarray, period: int = 11, rvi_ema_len: int = 100, source_type: str = "close",
        sequential: bool = False) -> Union[float, np.ndarray]:
    """
    RVI - Relative Volatility Index

    :param candles: np.ndarray
    :param period: int - default: 11
    :param rvi_ema_len: int - default: 100
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

    stdev = stddev(candles, period, sequential=True, source_type=source_type)
    source = get_candle_source(candles, source_type=source_type)

    diff = source - np.roll(source, -1)

    up = stdev * (diff >= 0)
    down = stdev * (diff < 0)

    up_avg = talib.EMA(up, rvi_ema_len)
    down_avg = talib.EMA(down, rvi_ema_len)

    result = 100 * (up_avg / (up_avg + down_avg))

    return result if sequential else result[-1]
