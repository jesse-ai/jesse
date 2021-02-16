from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, np_shift
from jesse.helpers import get_config


def vpt(candles: np.ndarray, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    Volume Price Trend (VPT)

    :param candles: np.ndarray
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

    source = get_candle_source(candles, source_type=source_type)
    vpt = (candles[:, 5] * ((source - np_shift(source, 1, fill_value=np.nan)) / np_shift(source, 1, fill_value=np.nan)))
    res = np_shift(vpt, 1, fill_value=np.nan) + vpt

    return res if sequential else res[-1]
