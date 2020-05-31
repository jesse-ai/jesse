import talib
import numpy as np


def engulfing(candles: np.ndarray, past=0) -> int:
    """
    is the current candle a engulfing pattern. returns 1 when is a bullish engulfing,
    and 0 when isn't, and -1 when is a bearish engulfing pattern.
    """
    if past != 0:
        candles = candles[:-abs(past)]

    if len(candles) > 240:
        candles = candles[-240:]

    res = talib.CDLENGULFING(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])[-1]

    return int(res / 100)
