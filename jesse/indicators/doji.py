import talib

from jesse.store import store


def doji(exchange, symbol, timeframe, past=0) -> int:
    """
    is the current candle a doji pattern. returns 1 when is a doji, and 0 when isn't
    """
    if past != 0:
        candles = store.candles.get_candles(exchange, symbol, timeframe)[:-abs(past)]
    else:
        candles = store.candles.get_candles(exchange, symbol, timeframe)

    if len(candles) > 240:
        candles = candles[-240:]

    res = talib.CDLDOJI(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])[-1]

    return int(res / 100)
