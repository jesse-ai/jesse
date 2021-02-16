from typing import Union

import numpy as np
import tulipy as ti

from jesse.helpers import get_candle_source
from jesse.helpers import get_config


def vidya(candles: np.ndarray, short_period: int = 2, long_period: int = 5, alpha: float = 0.2,
          source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    VIDYA - Variable Index Dynamic Average

    :param candles: np.ndarray
    :param short_period: int - default: 2
    :param long_period: int - default: 5
    :param alpha: float - default: 0.2
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

    source = get_candle_source(candles, source_type=source_type)
    res = ti.vidya(np.ascontiguousarray(source), short_period=short_period, long_period=long_period, alpha=alpha)

    return np.concatenate((np.full((candles.shape[0] - res.shape[0]), np.nan), res), axis=0) if sequential else res[-1]
