import talib

from jesse.store import store


def engulfing(exchange, symbol, timeframe, past=0) -> int:
    """
    is the current candle a engulfing pattern. returns 1 when is a bullish engulfing,
    and 0 when isn't, and -1 when is a bearish engulfing pattern.
    """
    if past != 0:
        candles = store.candles.get_candles(exchange, symbol, timeframe)[:-abs(past)]
    else:
        candles = store.candles.get_candles(exchange, symbol, timeframe)

    if len(candles) > 240:
        candles = candles[-240:]

    res = talib.CDLENGULFING(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])[-1]

    return int(res / 100)
