from typing import Union

import numpy as np

from jesse.helpers import get_candle_source
from jesse.helpers import get_config
from .high_pass_2_pole import high_pass_2_pole_fast


def decycler(candles: np.ndarray, hp_period: int = 125, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    Ehlers Simple Decycler

    :param candles: np.ndarray
    :param hp_period: int - default=125
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

    source = get_candle_source(candles, source_type=source_type)
    hp = high_pass_2_pole_fast(source, hp_period)
    res = source - hp

    if sequential:
        return res
    else:
        return None if np.isnan(res[-1]) else res[-1]
