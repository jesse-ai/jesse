import numpy as np


def get_candles(exchange: str, symbol: str, timeframe: str, start_date: str, finish_date: str) -> np.ndarray:
    """
    Returns candles from the database in numpy format

    :param exchange: str
    :param symbol: str
    :param timeframe: str
    :param start_date: str
    :param finish_date: str
    
    :return: np.ndarray
    """
    exchange = exchange.title()
    symbol = symbol.upper()

    import arrow

    import jesse.helpers as jh
    from jesse.models import Candle
    from jesse.exceptions import Breaker
    from jesse.services.candle import generate_candle_from_one_minutes

    start_date = jh.arrow_to_timestamp(arrow.get(start_date, 'YYYY-MM-DD'))
    finish_date = jh.arrow_to_timestamp(arrow.get(finish_date, 'YYYY-MM-DD')) - 60000

    # validate
    if start_date == finish_date:
        raise ValueError('start_date and finish_date cannot be the same.')
    if start_date > finish_date:
        raise ValueError('start_date cannot be bigger than finish_date.')
    if finish_date > arrow.utcnow().int_timestamp * 1000:
        raise ValueError('Can\'t backtest the future!')

    # fetch from database
    candles_tuple = Candle.select(
        Candle.timestamp, Candle.open, Candle.close, Candle.high, Candle.low,
        Candle.volume
    ).where(
        Candle.timestamp.between(start_date, finish_date),
        Candle.exchange == exchange,
        Candle.symbol == symbol).order_by(Candle.timestamp.asc()).tuples()

    candles = np.array(tuple(candles_tuple))

    # validate that there are enough candles for selected period
    if len(candles) == 0 or candles[-1][0] != finish_date or candles[0][0] != start_date:
        raise Breaker(f'Not enough candles for {symbol}. Try running "jesse import-candles"')

    if timeframe == '1m':
        return candles

    generated_candles = []
    for i in range(len(candles)):
        num = jh.timeframe_to_one_minutes(timeframe)

        if (i + 1) % num == 0:
            generated_candles.append(
                generate_candle_from_one_minutes(
                    timeframe,
                    candles[(i - (num - 1)):(i + 1)],
                    True
                )
            )

    return np.array(generated_candles)
