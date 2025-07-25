from typing import Union
import numpy as np
from jesse.helpers import get_candle_source, slice_candles
from jesse_rust import tema as tema_rust


def tema(candles: np.ndarray, period: int = 9, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    TEMA - Triple Exponential Moving Average

    :param candles: np.ndarray
    :param period: int - default: 9
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)

    if source.size == 0:
        return np.nan if not sequential else np.array([])

    res = tema_rust(source, period)
    
    return res if sequential else res[-1]

