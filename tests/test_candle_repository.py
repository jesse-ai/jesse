import peewee

from jesse.models.Candle import Candle
from jesse.repositories import candle_repository


def test_get_existing_candles_uses_one_query_for_all_pairs():
    database = peewee.SqliteDatabase(':memory:')

    with database.bind_ctx([Candle]):
        database.create_tables([Candle])
        Candle.insert_many([
            {
                'id': '00000000-0000-4000-8000-000000000001',
                'timestamp': 1704067200000,
                'open': 100,
                'close': 101,
                'high': 102,
                'low': 99,
                'volume': 10,
                'exchange': 'Binance Perpetual Futures',
                'symbol': 'BTC-USDT',
                'timeframe': '1m',
            },
            {
                'id': '00000000-0000-4000-8000-000000000002',
                'timestamp': 1709251200000,
                'open': 110,
                'close': 111,
                'high': 112,
                'low': 109,
                'volume': 20,
                'exchange': 'Binance Perpetual Futures',
                'symbol': 'BTC-USDT',
                'timeframe': '1h',
            },
            {
                'id': '00000000-0000-4000-8000-000000000003',
                'timestamp': 1706745600000,
                'open': 200,
                'close': 201,
                'high': 202,
                'low': 199,
                'volume': 30,
                'exchange': 'Binance Spot',
                'symbol': 'ETH-USDT',
                'timeframe': '1h',
            },
        ]).execute()

        statements = []
        database.connection().set_trace_callback(statements.append)

        result = candle_repository.get_existing_candles()

    select_statements = [
        statement for statement in statements
        if statement.lstrip().upper().startswith('SELECT')
    ]

    assert len(select_statements) == 1
    assert result == [
        {
            'exchange': 'Binance Perpetual Futures',
            'symbol': 'BTC-USDT',
            'start_date': '2024-01-01',
            'end_date': '2024-03-01',
        },
        {
            'exchange': 'Binance Spot',
            'symbol': 'ETH-USDT',
            'start_date': '2024-02-01',
            'end_date': '2024-02-01',
        },
    ]
