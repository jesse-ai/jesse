import peewee

from jesse.models.Candle import Candle
from jesse.repositories import candle_repository


def _candle_row(candle_id: str, timestamp: int, exchange: str, symbol: str, timeframe: str) -> dict:
    return {
        'id': candle_id,
        'timestamp': timestamp,
        'open': 100,
        'close': 101,
        'high': 102,
        'low': 99,
        'volume': 10,
        'exchange': exchange,
        'symbol': symbol,
        'timeframe': timeframe,
    }


def test_get_existing_candles_aggregates_timeframes_in_one_query():
    database = peewee.SqliteDatabase(':memory:')
    with database.bind_ctx([Candle]):
        database.create_tables([Candle])
        Candle.insert_many([
            # the start date comes from the 1m timeframe, the end date from the 1h timeframe
            _candle_row('00000000-0000-4000-8000-000000000001', 1704067200000, 'Binance Perpetual Futures', 'BTC-USDT', '1m'),
            _candle_row('00000000-0000-4000-8000-000000000002', 1706745600000, 'Binance Perpetual Futures', 'BTC-USDT', '1m'),
            _candle_row('00000000-0000-4000-8000-000000000003', 1709251200000, 'Binance Perpetual Futures', 'BTC-USDT', '1h'),
            _candle_row('00000000-0000-4000-8000-000000000004', 1706745600000, 'Binance Spot', 'ETH-USDT', '1h'),
            _candle_row('00000000-0000-4000-8000-000000000005', 1719792000000, 'Binance Spot', 'ETH-USDT', '1m'),
        ]).execute()

        statements = []
        database.connection().set_trace_callback(statements.append)

        result = candle_repository.get_existing_candles()

    # the whole listing must be a single round trip (the query starts with WITH)
    query_statements = [s for s in statements if s.lstrip().upper().startswith(('SELECT', 'WITH'))]
    assert len(query_statements) == 1

    assert result == [
        {
            'exchange': 'Binance Perpetual Futures',
            'symbol': 'BTC-USDT',
            'start_date': '2024-01-01',
            'end_date': '2024-03-01'
        },
        {
            'exchange': 'Binance Spot',
            'symbol': 'ETH-USDT',
            'start_date': '2024-02-01',
            'end_date': '2024-07-01'
        },
    ]


def test_get_existing_candles_returns_empty_list_for_empty_database():
    database = peewee.SqliteDatabase(':memory:')
    with database.bind_ctx([Candle]):
        database.create_tables([Candle])

        assert candle_repository.get_existing_candles() == []


def test_get_existing_candles_includes_rows_without_a_timeframe():
    # Databases created before the timeframe column existed keep those rows with a NULL timeframe.
    database = peewee.SqliteDatabase(':memory:')
    with database.bind_ctx([Candle]):
        database.execute_sql(
            'CREATE TABLE candle (id TEXT PRIMARY KEY, "timestamp" INTEGER NOT NULL, open REAL NOT NULL,'
            ' close REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, volume REAL NOT NULL,'
            ' exchange TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT)'
        )
        database.execute_sql(
            'CREATE UNIQUE INDEX candle_exchange_symbol_timeframe_timestamp'
            ' ON candle (exchange, symbol, timeframe, "timestamp")'
        )
        Candle.insert_many([
            # a pair whose legacy rows extend its 1m range on both ends
            _candle_row('00000000-0000-4000-8000-000000000001', 1704067200000, 'Binance Spot', 'BTC-USDT', None),
            _candle_row('00000000-0000-4000-8000-000000000002', 1706745600000, 'Binance Spot', 'BTC-USDT', '1m'),
            _candle_row('00000000-0000-4000-8000-000000000003', 1709251200000, 'Binance Spot', 'BTC-USDT', '1m'),
            _candle_row('00000000-0000-4000-8000-000000000004', 1719792000000, 'Binance Spot', 'BTC-USDT', None),
            # a pair that only has legacy rows, between two regular pairs
            _candle_row('00000000-0000-4000-8000-000000000005', 1706745600000, 'Binance Spot', 'ETH-USDT', None),
            _candle_row('00000000-0000-4000-8000-000000000006', 1709251200000, 'Binance Spot', 'ETH-USDT', None),
            _candle_row('00000000-0000-4000-8000-000000000007', 1704067200000, 'Binance Spot', 'SOL-USDT', '1m'),
        ]).execute()

        result = candle_repository.get_existing_candles()

    assert result == [
        {'exchange': 'Binance Spot', 'symbol': 'BTC-USDT', 'start_date': '2024-01-01', 'end_date': '2024-07-01'},
        {'exchange': 'Binance Spot', 'symbol': 'ETH-USDT', 'start_date': '2024-02-01', 'end_date': '2024-03-01'},
        {'exchange': 'Binance Spot', 'symbol': 'SOL-USDT', 'start_date': '2024-01-01', 'end_date': '2024-01-01'},
    ]
