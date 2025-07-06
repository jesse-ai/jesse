from typing import Union
import numpy as np
from jesse.helpers import get_candle_source, slice_candles
from jesse_rust import bollinger_bands_width as bollinger_bands_width_rust


def bollinger_bands_width(candles: np.ndarray, period: int = 20, mult: float = 2.0, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    BBW - Bollinger Bands Width

    :param candles: np.ndarray
    :param period: int - default: 20
    :param mult: float - default: 2
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)
    
    result = bollinger_bands_width_rust(source, period, float(mult))
    
    return result if sequential else result[-1]
