import talib

from jesse.store import store


def hammer(exchange, symbol, timeframe, past=0) -> int:
    """
    is the current candle a hammer pattern. returns 1 when is a hammer, and 0 when isn't
    """
    if past != 0:
        candles = store.candles.get_candles(exchange, symbol, timeframe)[:-abs(past)]
    else:
        candles = store.candles.get_candles(exchange, symbol, timeframe)

    if len(candles) > 240:
        candles = candles[-240:]

    res = talib.CDLHAMMER(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])[-1]

    return int(res / 100)


def inverted_hammer(exchange, symbol, timeframe) -> int:
    """
    is the current candle a inverted_hammer pattern. returns 1 when is a inverted_hammer, and 0 when isn't
    """
    candles = store.candles.get_candles(exchange, symbol, timeframe)

    if len(candles) > 240:
        candles = candles[-240:]

    res = talib.CDLINVERTEDHAMMER(candles[:, 1], candles[:, 3], candles[:, 4], candles[:, 2])[-1]

    return int(res / 100)
