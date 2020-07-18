from typing import Union

import numpy as np
import talib


def chande(candles: np.ndarray, period=22, mult=3.0, direction="long", sequential=False) -> Union[float, np.ndarray]:
    """
    Chandelier Exits

    :param candles: np.ndarray
    :param period: int - default: 22
    :param period: float - default: 3.0
    :param direction: str - default: "long"
    :param sequential: bool - default=False

    :return: float | np.ndarray
    """
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    candles_close = candles[:, 2]
    candles_high = candles[:, 3]
    candles_low = candles[:, 4]

    atr = talib.ATR(candles_high, candles_low, candles_close, timeperiod=period)

    maxp = np.zeros(len(candles_high) - period + 1)
    if direction == 'long':
        for i in range(period - 1, len(candles_high)):
            maxp[i - period + 1] = np.amax(candles_high[i - period + 1:i + 1])
        maxp = np.concatenate((np.full((candles.shape[0] - maxp.shape[0]), np.nan), maxp))
        result = maxp - atr * mult
    elif direction == 'short':
        for i in range(period - 1, len(candles_high)):
            maxp[i - period + 1] = np.amin(candles_low[i - period + 1:i + 1])
        maxp = np.concatenate((np.full((candles.shape[0] - maxp.shape[0]), np.nan), maxp))
        result = maxp + atr * mult
    else:
        print('The last parameter must be \'short\' or \'long\'')

    return result if sequential else result[-1]
