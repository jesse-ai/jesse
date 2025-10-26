from typing import Union
import numpy as np
from jesse.helpers import slice_candles
from jesse_rust import atr as rust_atr


def atr(candles: np.ndarray, period: int = 14, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    ATR - Average True Range using optimized Rust implementation

    :param candles: np.ndarray
    :param period: int - default: 14
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    result = rust_atr(candles, period)
    
    return result if sequential else result[-1]
