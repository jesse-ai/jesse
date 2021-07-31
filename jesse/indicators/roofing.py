from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, slice_candles
from .high_pass_2_pole import high_pass_2_pole_fast
from .supersmoother import supersmoother_fast


def roofing(candles: np.ndarray, hp_period: int = 48, lp_period: int = 10, source_type: str = "close",
            sequential: bool = False) -> Union[float, np.ndarray]:
    """
    Roofing Filter indicator by John F. Ehlers

    :param candles: np.ndarray
    :param hp_period: int - default: 48
    :param lp_period: int - default: 10
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
        """

    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)

    hpf = high_pass_2_pole_fast(source, hp_period)

    res = supersmoother_fast(hpf, lp_period)

    return res if sequential else res[-1]
