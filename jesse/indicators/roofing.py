from typing import Union

import numpy as np

from .high_pass import high_pass
from .supersmoother import supersmoother


def roofing(candles: np.ndarray, hp_period=48, lp_period=10, source_type="close", sequential=False) -> Union[
    float, np.ndarray]:
    """
    Roofing Filter indicator by John F. Ehlers

    :param candles: np.ndarray
    :param period: int - default=20
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """

    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    hpf = high_pass(candles, period=hp_period, source_type=source_type, sequential=True)

    res = supersmoother(hpf, cutoff=lp_period, sequential=True)

    if sequential:
        return res
    else:
        return None if np.isnan(res[-1]) else res[-1]
