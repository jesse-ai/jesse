import threading

import numpy as np

import jesse.helpers as jh
from jesse.models.Candle import Candle
from jesse.models.Orderbook import Orderbook
from jesse.models.Ticker import Ticker
from jesse.models.Trade import Trade


def store_candle_into_db(exchange: str, symbol: str, candle: np.ndarray):
    """
    store candle into the database
    """
    d = {
        'id': jh.generate_unique_id(),
        'symbol': symbol,
        'exchange': exchange,
        'timestamp': candle[0],
        'open': candle[1],
        'high': candle[3],
        'low': candle[4],
        'close': candle[2],
        'volume': candle[5]
    }

    def async_save():
        Candle.insert(**d).on_conflict_ignore().execute()
        print(
            jh.color(
                'candle: {}-{}-{}: {}'.format(jh.timestamp_to_time(d['timestamp']), exchange, symbol, candle),
                'blue'
            )
        )

    # async call
    threading.Thread(target=async_save).start()


def store_ticker_into_db(exchange: str, symbol: str, ticker: np.ndarray):
    """

    :param exchange:
    :param symbol:
    :param ticker:
    """
    d = {
        'id': jh.generate_unique_id(),
        'timestamp': ticker[0],
        'last_price': ticker[1],
        'high_price': ticker[2],
        'low_price': ticker[3],
        'volume': ticker[4],
        'symbol': symbol,
        'exchange': exchange,
    }

    def async_save():
        Ticker.insert(**d).on_conflict_ignore().execute()
        print(
            jh.color('ticker: {}-{}-{}: {}'.format(
                jh.timestamp_to_time(d['timestamp']), exchange, symbol, ticker
            ), 'yellow')
        )

    # async call
    threading.Thread(target=async_save).start()


def store_trade_into_db(exchange: str, symbol: str, trade: np.ndarray):
    """

    :param exchange:
    :param symbol:
    :param trade:
    """
    d = {
        'id': jh.generate_unique_id(),
        'timestamp': trade[0],
        'price': trade[1],
        'buy_qty': trade[2],
        'sell_qty': trade[3],
        'buy_count': trade[4],
        'sell_count': trade[5],
        'symbol': symbol,
        'exchange': exchange,
    }

    def async_save():
        Trade.insert(**d).on_conflict_ignore().execute()
        print(
            jh.color(
                'trade: {}-{}-{}: {}'.format(
                    jh.timestamp_to_time(d['timestamp']), exchange, symbol, trade
                ),
                'green'
            )
        )

    # async call
    threading.Thread(target=async_save).start()


def store_orderbook_into_db(exchange: str, symbol: str, orderbook: np.ndarray):
    """

    :param exchange:
    :param symbol:
    :param orderbook:
    """
    d = {
        'id': jh.generate_unique_id(),
        'timestamp': jh.now(),
        'data': orderbook.dumps(),
        'symbol': symbol,
        'exchange': exchange,
    }

    def async_save():
        Orderbook.insert(**d).on_conflict_ignore().execute()
        print(
            jh.color(
                'orderbook: {}-{}-{}: [{}, {}], [{}, {}]'.format(
                    jh.timestamp_to_time(d['timestamp']), exchange, symbol,
                    # best ask
                    orderbook[0][0][0], orderbook[0][0][1],
                    # best bid
                    orderbook[1][0][0], orderbook[1][0][1]
                ),
                'magenta'
            )
        )

    # async call
    threading.Thread(target=async_save).start()


def fetch_candles_from_db(exchange: str, symbol: str, start_date: int, finish_date: int) -> tuple:
    """

    :param exchange:
    :param symbol:
    :param start_date:
    :param finish_date:
    :return:
    """
    candles_tuple = tuple(
        Candle.select(
            Candle.timestamp, Candle.open, Candle.close, Candle.high, Candle.low,
            Candle.volume
        ).where(
            Candle.timestamp.between(start_date, finish_date),
            Candle.exchange == exchange,
            Candle.symbol == symbol
        ).order_by(Candle.timestamp.asc()).tuples()
    )

    return candles_tuple
