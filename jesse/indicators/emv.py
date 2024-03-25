from typing import Union

import numpy as np
import tulipy as ti

from jesse.helpers import same_length, slice_candles


def emv(candles: np.ndarray, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    EMV - Ease of Movement

    :param candles: np.ndarray
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    res = ti.emv(np.ascontiguousarray(candles[:, 3]), np.ascontiguousarray(candles[:, 4]),
                 np.ascontiguousarray(candles[:, 5]))

    return same_length(candles, res) if sequential else res[-1]
