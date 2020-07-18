from typing import Union

import numpy as np
import talib

from jesse.helpers import get_candle_source


def efi(candles: np.ndarray, period=13, source_type="close", sequential=False) -> Union[float, np.ndarray]:
    """
    EFI - Elders Force Index

    :param candles: np.ndarray
    :param period: int - default: 13
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)

    dif = np.zeros(len(source) - 1)
    for i in range(1, len(source)):
        dif[i - 1] = (source[i] - source[i - 1]) * candles[:, 5][i]

    res = talib.EMA(dif, timeperiod=period)
    res_with_nan = np.concatenate((np.full((candles.shape[0] - res.shape[0]), np.nan), res))

    return res_with_nan if sequential else res_with_nan[-1]
