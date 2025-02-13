from typing import Union
import numpy as np
from jesse.helpers import slice_candles
from jesse.indicators import ema


def kvo(candles: np.ndarray, short_period: int = 34, long_period: int = 55, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    KVO - Klinger Volume Oscillator

    :param candles: np.ndarray
    :param short_period: int - default: 34
    :param long_period: int - default: 55
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)

    # Calculate HLC3
    hlc3 = (candles[:, 3] + candles[:, 4] + candles[:, 2]) / 3

    # Calculate momentum (change in HLC3)
    mom = np.diff(hlc3, prepend=hlc3[0])

    # Calculate trend
    trend = np.zeros_like(mom)
    trend[1:] = np.where(mom[1:] > 0, 1, np.where(mom[1:] < 0, -1, trend[:-1]))

    # Daily Measurement (High - Low)
    dm = candles[:, 3] - candles[:, 4]

    # Cumulative Measurement
    cm = np.zeros_like(dm)
    for i in range(1, len(trend)):
        if trend[i] == trend[i-1]:
            cm[i] = cm[i-1] + dm[i]
        else:
            cm[i] = dm[i] + dm[i-1]

    # Volume Force
    volume = candles[:, 5]
    with np.errstate(divide='ignore', invalid='ignore'):
        expr = np.abs(np.divide(2 * dm, cm, out=np.zeros_like(dm, dtype=float), where=cm != 0) - 1)
    vf = 100 * volume * trend * expr
    vf[cm == 0] = 0

    # Calculate EMAs
    fast_ema = ema(vf, period=short_period, sequential=True)
    slow_ema = ema(vf, period=long_period, sequential=True)
    res = fast_ema - slow_ema
    return res if sequential else res[-1]
