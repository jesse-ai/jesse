from typing import Union
import numpy as np
from jesse.helpers import slice_candles
from jesse_rust import adx as adx_rust


def adx(candles: np.ndarray, period: int = 14, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    ADX - Average Directional Movement Index

    :param candles: np.ndarray, expected 2D array with OHLCV data where index 3 is high, index 4 is low, and index 2 is close
    :param period: int - default: 14
    :param sequential: bool - if True, return full series, else return last value
    :return: float | np.ndarray
    """
    if len(candles.shape) < 2:
        raise ValueError("adx indicator requires a 2D array of candles")
        
    candles = slice_candles(candles, sequential)

    # Ensure there's enough data
    if len(candles) <= 2 * period:
        return np.nan if not sequential else np.full(len(candles), np.nan)

    result = adx_rust(candles, period)

    return result if sequential else result[-1]
