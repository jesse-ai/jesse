from typing import Union

import numpy as np
from jesse.helpers import slice_candles
from numba import njit


def sar(candles: np.ndarray, acceleration: float = 0.02, maximum: float = 0.2, sequential: bool = False) -> Union[float, np.ndarray]:
    """
    SAR - Parabolic SAR

    :param candles: np.ndarray
    :param acceleration: float - default: 0.02
    :param maximum: float - default: 0.2
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)
    # Assuming candle format where index 3 is high and index 4 is low
    high = candles[:, 3]
    low = candles[:, 4]

    n = len(candles)
    if n == 0:
        return np.array([])
    if n < 2:
        return low[-1]

    # Use numba-compiled function to calculate SAR values
    sar_values = _fast_sar(high, low, acceleration, maximum, n)
    return sar_values if sequential else sar_values[-1]


@njit(cache=True)
def _fast_sar(high, low, acceleration, maximum, n):
    sar_values = np.zeros(n)
    if high[1] > high[0]:
        uptrend = True
        sar_values[0] = low[0]
        ep = high[0]  # extreme point
    else:
        uptrend = False
        sar_values[0] = high[0]
        ep = low[0]
    af = acceleration  # initial acceleration factor
    for i in range(1, n):
        prev_sar = sar_values[i - 1]
        if uptrend:
            sar_temp = prev_sar + af * (ep - prev_sar)
            if i >= 2:
                sar_temp = min(sar_temp, low[i - 1], low[i - 2])
            else:
                sar_temp = min(sar_temp, low[i - 1])
        else:
            sar_temp = prev_sar - af * (prev_sar - ep)
            if i >= 2:
                sar_temp = max(sar_temp, high[i - 1], high[i - 2])
            else:
                sar_temp = max(sar_temp, high[i - 1])

        if uptrend:
            if low[i] < sar_temp:
                sar_temp = ep
                uptrend = False
                af = acceleration  # reset acceleration factor
                ep = low[i]
            else:
                if high[i] > ep:
                    ep = high[i]
                    af = af + acceleration
                    if af > maximum:
                        af = maximum
        else:
            if high[i] > sar_temp:
                sar_temp = ep
                uptrend = True
                af = acceleration
                ep = high[i]
            else:
                if low[i] < ep:
                    ep = low[i]
                    af = af + acceleration
                    if af > maximum:
                        af = maximum

        sar_values[i] = sar_temp
    return sar_values
