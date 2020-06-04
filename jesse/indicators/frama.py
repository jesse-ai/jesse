import math
from typing import Union

import numpy as np


def frama(candles: np.ndarray, window=10, FC=1, SC=300, sequential=False) -> Union[float, np.ndarray]:
    """
    Fractal Adaptive Moving Average (FRAMA)

    :param candles: np.ndarray
    :param window: int - default: 10
    :param FC: int - default: 1
    :param SC: int - default: 300
    :param sequential: bool - default=False

    :return:  float | np.ndarray
    """

    if len(candles) > 240:
        candles = candles[-240:]

    n = window

    # n must be even
    if n % 2 == 1:
        print("FRAMA n must be even. Adding one")
        n += 1

    w = math.log(2.0 / (SC + 1))

    D = np.zeros(len(candles))
    D[:n] = np.NaN

    alphas = np.zeros(len(candles))
    alphas[:n] = np.NaN

    for i in range(n, len(candles)):
        per = candles[i - n:i]

        # take 2 batches of the input
        split = np.split(per, 2)
        v1 = split[0]
        v2 = split[1]

        N1 = (np.max(v1[:, 3]) - np.min(v1[:, 4])) / (n / 2)
        N2 = (np.max(v2[:, 3]) - np.min(v2[:, 4])) / (n / 2)
        N3 = (np.max(per[:, 3]) - np.min(per[:, 4])) / n

        if N1 > 0 and N2 > 0 and N3 > 0:
            D[i] = (math.log(N1 + N2) - math.log(N3)) / math.log(2)
        else:
            D[i] = D[i - 1]

        oldalpha = math.exp(w * (D[i] - 1))
        # keep btwn 1 & 0.01
        oldalpha = np.max([oldalpha, 0.1])
        oldalpha = np.min([oldalpha, 1])

        oldN = (2 - oldalpha) / oldalpha
        N = ((SC - FC) * ((oldN - 1) / (SC - 1))) + FC
        alpha_ = 2 / (N + 1)
        if alpha_ < 2 / (SC + 1):
            alphas[i] = 2 / (SC + 1)
        elif alpha_ > 1:
            alphas[i] = 1
        else:
            alphas[i] = alpha_

    frama = np.zeros(len(candles))
    frama[n - 1] = np.mean(candles[:, 2][:n])
    frama[:n - 1] = np.NaN

    for i in range(n, len(frama)):
        frama[i] = (alphas[i] * candles[:, 2][i]) + (1 - alphas[i]) * frama[i - 1]

    if sequential:
        return frama
    else:
        return frama[-1]
