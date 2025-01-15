from typing import Union
from jesse.indicators.sma import sma
import numpy as np


def vosc(candles: np.ndarray, short_period: int = 2, long_period: int = 5, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    VOSC - Volume Oscillator

    :param candles: np.ndarray
    :param short_period: int - default: 2
    :param long_period: int - default: 5
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    from jesse.helpers import same_length, slice_candles

    candles = slice_candles(candles, sequential)
    volume = candles[:, 5]

    short_sma = sma(volume, short_period, sequential=True)
    long_sma = sma(volume, long_period, sequential=True)

    vosc_values = (short_sma - long_sma) / long_sma * 100

    vosc_result = same_length(candles, vosc_values)

    return vosc_result if sequential else vosc_result[-1]
