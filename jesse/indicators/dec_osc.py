from typing import Union

import numpy as np

from jesse.helpers import get_candle_source


def dec_osc(candles: np.ndarray, hp_period=125, k=1, source_type="close", sequential=False) -> Union[float, np.ndarray]:
    """
    Ehlers Decycler Oscillator

    :param candles: np.ndarray
    :param hp_period: int - default=125
    :param k: float - default=1
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)
    alphaArg1 = 2 * np.pi * 0.707 / hp_period
    alpha1 = (np.cos(alphaArg1) + np.sin(alphaArg1) - 1) / np.cos(alphaArg1)
    coeff1 = np.array([(1 - alpha1 / 2) ** 2, 2 * (1 - alpha1), -(1 - alpha1) ** 2])
    hp1 = np.copy(source)

    alphaArg2 = 2 * np.pi * 0.707 / (0.5 * hp_period)
    alpha2 = (np.cos(alphaArg2) + np.sin(alphaArg2) - 1) / np.cos(alphaArg2)
    coeff2 = np.array([(1 - alpha2 / 2) ** 2, 2 * (1 - alpha2), -(1 - alpha2) ** 2])
    hp2 = np.copy(source)

    for i in range(source.shape[0]):
        val1 = np.array([source[i] - 2 * source[i - 1] + source[i - 2], hp1[i - 1], hp1[i - 2]])
        hp1[i] = np.matmul(coeff1, val1)

        val2 = np.array(
            [(source[i] - hp1[i]) - 2 * (source[i - 1] - hp1[i - 1]) + (source[i - 2] - hp1[i - 2]), hp2[i - 1],
             hp2[i - 2]])
        hp2[i] = np.matmul(coeff2, val2)

    res = 100 * k * hp2 / source

    if sequential:
        return res
    else:
        return None if np.isnan(res[-1]) else res[-1]
