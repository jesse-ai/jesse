from typing import Union

import numpy as np
import tulipy as ti


def wad(candles: np.ndarray, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    WAD - Williams Accumulation/Distribution

    :param candles: np.ndarray
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    res = ti.wad(np.ascontiguousarray(candles[:, 3]), np.ascontiguousarray(candles[:, 4]),
                 np.ascontiguousarray(candles[:, 1]))

    return np.concatenate((np.full((candles.shape[0] - res.shape[0]), np.nan), res), axis=0) if sequential else res[-1]
