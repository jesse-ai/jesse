import numpy as np
import talib
from typing import Union


def ao(candles: np.ndarray, sequential=False) -> Union[float, np.ndarray]:
    """
    Awesome Oscillator

    :param candles: np.ndarray
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    med = talib.MEDPRICE(candles[:, 3], candles[:, 4])
    res = talib.SMA(med,5) - talib.SMA(med,34)

    return res if sequential else res[-1]
