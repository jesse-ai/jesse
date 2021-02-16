from typing import Union

import numpy as np
import talib

from jesse.helpers import get_config


def sar(candles: np.ndarray, acceleration: float = 0.02, maximum: float = 0.2, sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    SAR - Parabolic SAR

    :param candles: np.ndarray
    :param acceleration: float - default: 0.02
    :param maximum: float - default: 0.2
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

    res = talib.SAR(candles[:, 3], candles[:, 4], acceleration=acceleration, maximum=maximum)

    return res if sequential else res[-1]
