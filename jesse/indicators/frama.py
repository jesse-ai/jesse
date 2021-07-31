from typing import Union

import numpy as np
try:
    from numba import njit
except ImportError:
    njit = lambda a : a

from jesse.helpers import slice_candles


def frama(candles: np.ndarray, window: int = 10, FC: int = 1, SC: int = 300, sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    Fractal Adaptive Moving Average (FRAMA)

    :param candles: np.ndarray
    :param window: int - default: 10
    :param FC: int - default: 1
    :param SC: int - default: 300
    :param sequential: bool - default: False

    :return:  float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    n = window

    # n must be even
    if n % 2 == 1:
        print("FRAMA n must be even. Adding one")
        n += 1

    res = frame_fast(candles, n, SC, FC)

    if sequential:
        return res
    else:
        return res[-1]


@njit
def frame_fast(candles, n, SC, FC):
    w = np.log(2.0 / (SC + 1))

    D = np.zeros(candles.size)
    D[:n] = np.NaN

    alphas = np.zeros(candles.size)
    alphas[:n] = np.NaN

    for i in range(n, candles.shape[0]):
        per = candles[i - n:i]

        v1 = per[per.shape[0] // 2:]
        v2 = per[:per.shape[0] // 2]

        N1 = (max(v1[:, 3]) - min(v1[:, 4])) / (n / 2)
        N2 = (max(v2[:, 3]) - min(v2[:, 4])) / (n / 2)
        N3 = (max(per[:, 3]) - min(per[:, 4])) / n

        if N1 > 0 and N2 > 0 and N3 > 0:
            D[i] = (np.log(N1 + N2) - np.log(N3)) / np.log(2)
        else:
            D[i] = D[i - 1]

        oldalpha = np.exp(w * (D[i] - 1))
        # keep btwn 1 & 0.01
        oldalpha = max([oldalpha, 0.1])
        oldalpha = min([oldalpha, 1])

        oldN = (2 - oldalpha) / oldalpha
        N = ((SC - FC) * ((oldN - 1) / (SC - 1))) + FC
        alpha_ = 2 / (N + 1)
        if alpha_ < 2 / (SC + 1):
            alphas[i] = 2 / (SC + 1)
        elif alpha_ > 1:
            alphas[i] = 1
        else:
            alphas[i] = alpha_

    frama_val = np.zeros(candles.shape[0])
    frama_val[n - 1] = np.mean(candles[:, 2][:n])
    frama_val[:n - 1] = np.NaN

    for i in range(n, frama_val.shape[0]):
        frama_val[i] = (alphas[i] * candles[:, 2][i]) + (1 - alphas[i]) * frama_val[i - 1]
    return frama_val
