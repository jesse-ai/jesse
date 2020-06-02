from typing import Union

import numpy as np
import talib



def dx(candles: np.ndarray, period=14, sequential=False) -> Union[float, np.ndarray]:
    """
    DX - Directional Movement Index

    :param candles: np.ndarray
    :param period: int - default: 14
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    res = talib.DX(candles[:, 3], candles[:, 4], candles[:, 2], timeperiod=period)

    return res if sequential else res[-1]
