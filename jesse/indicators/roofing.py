from typing import Union

import numpy as np

from jesse.helpers import get_candle_source
from jesse.helpers import get_config
from .high_pass_2_pole import high_pass_2_pole_fast
from .supersmoother import supersmoother_fast


def roofing(candles: np.ndarray, hp_period: int = 48, lp_period: int = 10, source_type: str = "close",
            sequential: bool = False) -> Union[float, np.ndarray]:
    """
    Roofing Filter indicator by John F. Ehlers

    :param candles: np.ndarray
    :param period: int - default=20
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
        """

    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
        candles = candles[-warmup_candles_num:]

    source = get_candle_source(candles, source_type=source_type)

    hpf = high_pass_2_pole_fast(source, hp_period)

    res = supersmoother_fast(hpf, lp_period)

    if sequential:
        return res
    else:
        return None if np.isnan(res[-1]) else res[-1]
