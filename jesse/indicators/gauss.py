import math
from typing import Union

import numpy as np

from jesse.helpers import get_candle_source


def gauss(candles: np.ndarray, period=14, poles=4, source_type="close", sequential=False) -> Union[float, np.ndarray]:
    """
    Gaussian Filter

    :param candles: np.ndarray
    :param period: int - default=14
    :param poles: int - default=4
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """

    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)
    N = len(source)
    source = source[~np.isnan(source)]
    to_fill = N - len(source)
    PI = math.pi
    beta = (1 - math.cos(2 * PI / period)) / (math.pow(2, 1 / poles) - 1)
    alpha = -beta + math.sqrt(math.pow(beta, 2) + 2 * beta)

    fil = np.zeros(poles + len(source))
    if poles == 1:
        coeff = np.array([alpha, (1 - alpha)])
    elif poles == 2:
        coeff = np.array([alpha ** 2, 2 * (1 - alpha), -(1 - alpha) ** 2])
    elif poles == 3:
        coeff = np.array([alpha ** 3, 3 * (1 - alpha), -3 * (1 - alpha) ** 2, (1 - alpha) ** 3])
    elif poles == 4:
        coeff = np.array([alpha ** 4, 4 * (1 - alpha), -6 * (1 - alpha) ** 2, 4 * (1 - alpha) ** 3, -(1 - alpha) ** 4])

    for i in range(len(source)):
        if poles == 1:
            val = np.array([source[i].item(), fil[i]])
        elif poles == 2:
            val = np.array([source[i].item(), fil[1 + i], fil[i]])
        elif poles == 3:
            val = np.array([source[i].item(), fil[2 + i], fil[1 + i], fil[i]])
        elif poles == 4:
            val = np.array([source[i].item(), fil[3 + i], fil[2 + i], fil[1 + i], fil[i]])

        fil[poles + i] = np.dot(coeff, val)

    if to_fill != 0:
        res = np.insert(fil[poles:], 0, np.repeat(np.nan, to_fill))
    else:
        res = fil[poles:]

    if sequential:
        return res
    else:
        return None if np.isnan(res[-1]) else res[-1]
