from typing import Union

import numpy as np
import tulipy as ti

from jesse.helpers import slice_candles, same_length


def wad(candles: np.ndarray, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    WAD - Williams Accumulation/Distribution

    :param candles: np.ndarray
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    res = ti.wad(np.ascontiguousarray(candles[:, 3]), np.ascontiguousarray(candles[:, 4]),
                 np.ascontiguousarray(candles[:, 1]))

    return same_length(candles, res) if sequential else res[-1]
