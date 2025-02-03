from typing import Union

import numpy as np

from jesse.helpers import slice_candles


def bop(candles: np.ndarray, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    BOP - Balance Of Power

    :param candles: np.ndarray
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    open_prices = candles[:, 1]
    high_prices = candles[:, 3]
    low_prices = candles[:, 4]
    close_prices = candles[:, 2]
    denominator = high_prices - low_prices
    bop_values = np.where(denominator != 0, (close_prices - open_prices) / denominator, 0)

    return bop_values if sequential else bop_values[-1]
