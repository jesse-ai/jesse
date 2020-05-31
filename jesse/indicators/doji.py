import talib
import numpy as np


def doji(candles: np.ndarray, past=0) -> int:
    """
    is the current candle a doji pattern. returns 1 when is a doji, and 0 when isn't
    """
    if past != 0:
        candles = candles[:-abs(past)]

    if len(candles) > 240:
        candles = candles[-240:]

    res = talib.CDLDOJI(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])[-1]

    return int(res / 100)
