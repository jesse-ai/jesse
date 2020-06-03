from typing import Union

import numpy as np


def lrsi(candles: np.ndarray, alpha=0.2, sequential=False) -> Union[float, np.ndarray]:
    """
    RSI Laguerre Filter

    :param candles: np.ndarray
    :param alpha: float - default=0.2
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    price = (candles[:, 3] + candles[:, 4]) / 2

    l0 = np.copy(price)
    l1 = np.copy(price)
    l2 = np.copy(price)
    l3 = np.copy(price)

    for i in range(l0.shape[0]):
        gamma = 1 - alpha
        l0[i] = alpha * price[i] + gamma * l0[i - 1]
        l1[i] = -gamma * l0[i] + l0[i - 1] + gamma * l1[i - 1]
        l2[i] = -gamma * l1[i] + l1[i - 1] + gamma * l2[i - 1]
        l3[i] = -gamma * l2[i] + l2[i - 1] + gamma * l3[i - 1]

    rsi = np.zeros_like(price)
    for i in range(candles[:, 2].shape[0]):
        cu = 0
        cd = 0

        if l0[i] >= l1[i]:
            cu = l0[i] - l1[i]
        else:
            cd = l1[i] - l0[i]

        if l1[i] >= l2[i]:
            cu = cu + l1[i] - l2[i]
        else:
            cd = cd + l2[i] - l1[i]

        if l2[i] >= l3[i]:
            cu = cu + l2[i] - l3[i]
        else:
            cd = cd + l3[i] - l2[i]

        if cu + cd == 0:
            rsi[i] = 0
        else:
            rsi[i] = cu / (cu + cd)

    if sequential:
        return rsi
    else:
        return None if np.isnan(rsi[-1]) else rsi[-1]
