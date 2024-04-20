from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, slice_candles

from .high_pass_2_pole import high_pass_2_pole_fast


def dec_osc(candles: np.ndarray, hp_period: int = 125, k: float = 1, source_type: str = "close",
            sequential: bool = False) -> Union[float, np.ndarray]:
    """
    Ehlers Decycler Oscillator

    :param candles: np.ndarray
    :param hp_period: int - default: 125
    :param k: float - default: 1
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    source = get_candle_source(candles, source_type=source_type)

    hp = high_pass_2_pole_fast(source, hp_period)
    dec = source - hp
    decosc = high_pass_2_pole_fast(dec, 0.5 * hp_period)

    res = 100 * k * decosc / source

    return res if sequential else res[-1]
