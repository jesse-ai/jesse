from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, np_shift


def vpt(candles: np.ndarray, source_type="close", sequential=False) -> Union[float, np.ndarray]:
    """
    Volume Price Trend (VPT)

    :param candles: np.ndarray
    :param source_type: str - default: "close"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    source = get_candle_source(candles, source_type=source_type)
    vpt = (candles[:, 5] * ((source - np_shift(source, 1, fill_value=np.nan)) / np_shift(source, 1, fill_value=np.nan)))
    res = np_shift(vpt, 1, fill_value=np.nan) + vpt
    
    return res if sequential else res[-1]

