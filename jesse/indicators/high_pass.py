import math
from typing import Union

import numpy as np
from jesse.helpers import get_candle_source



def high_pass(candles: np.ndarray, period=48, source_type="close", sequential=False) -> Union[float, np.ndarray]:
    """
    High Pass Filter indicator by John F. Ehlers

    :param candles: np.ndarray
    :param period: int - default=48
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """

    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)

    hpf = np.full_like(source, 0)

    for i in range(source.shape[0]):
        if not (i < 2):
            alpha_arg = 2 * math.pi / (period * 1.414)
            alpha1 = (math.cos(alpha_arg) + math.sin(alpha_arg) - 1) / math.cos(alpha_arg)
            hpf[i] = math.pow(1.0 - alpha1 / 2.0, 2) * (source[i] - 2 * source[i - 1] + source[i - 2]) + 2 * (1 - alpha1) * hpf[i - 1] - math.pow(1 - alpha1, 2) * hpf[i - 2]

    if sequential:
        return hpf
    else:
        return None if np.isnan(hpf[-1]) else hpf[-1]
