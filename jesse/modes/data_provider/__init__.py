import numpy as np
import jesse.helpers as jh
from jesse.models import Candle
from jesse.services.candle import generate_candle_from_one_minutes


def get_candles(exchange: str, symbol: str, timeframe: str):
    exchange = exchange.title()
    symbol = symbol.upper()

    one_min_count = jh.timeframe_to_one_minutes(timeframe)
    finish_date = jh.now()
    start_date = finish_date - (210 * one_min_count * 60_000)

    # fetch from database
    candles_tuple = Candle.select(
        Candle.timestamp, Candle.open, Candle.close, Candle.high, Candle.low,
        Candle.volume
    ).where(
        Candle.timestamp.between(start_date, finish_date),
        Candle.exchange == exchange,
        Candle.symbol == symbol).order_by(Candle.timestamp.asc()).tuples()

    candles = np.array(tuple(candles_tuple))

    if timeframe != '1m':
        generated_candles = []
        for i in range(len(candles)):
            if (i + 1) % one_min_count == 0:
                generated_candles.append(
                    generate_candle_from_one_minutes(
                        timeframe,
                        candles[(i - (one_min_count - 1)):(i + 1)],
                        True
                    )
                )
        candles = generated_candles

    return [
        {
            'time': int(c[0] / 1000),
            'open': c[1],
            'close': c[2],
            'high': c[3],
            'low': c[4],
            'volume': c[5],
        } for c in candles
    ]
