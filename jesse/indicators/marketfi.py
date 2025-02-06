from typing import Union

import numpy as np

from jesse.helpers import same_length, slice_candles


def marketfi(candles: np.ndarray, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    MARKETFI - Market Facilitation Index
    Formula: (High - Low) / Volume

    :param candles: np.ndarray
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    # high is at index 3, low at index 4, volume at index 5
    res = (candles[:, 3] - candles[:, 4]) / candles[:, 5]

    return same_length(candles, res) if sequential else res[-1]
