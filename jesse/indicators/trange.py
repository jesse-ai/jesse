from typing import Union

import numpy as np

from jesse.helpers import slice_candles


def trange(candles: np.ndarray, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    TRANGE - True Range

    :param candles: np.ndarray
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)
    high = candles[:, 3]
    low = candles[:, 4]
    close = candles[:, 2]

    true_range = np.empty_like(high)
    true_range[0] = high[0] - low[0]

    if len(candles) > 1:
        diff_hl = high[1:] - low[1:]
        diff_hpc = np.abs(high[1:] - close[:-1])
        diff_lpc = np.abs(low[1:] - close[:-1])
        true_range[1:] = np.maximum(np.maximum(diff_hl, diff_hpc), diff_lpc)

    res = true_range
    return res if sequential else res[-1]
