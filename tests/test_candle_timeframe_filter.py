import peewee
import pytest

import jesse.helpers as jh
from jesse.models.Candle import Candle
from jesse.services import candle_service

# The candle queries must match 1m candles *and* legacy rows whose timeframe was never
# set (NULL). That condition has to be built with peewee's `|` operator: Python's own
# `or` returns the left-hand Expression as soon as it sees a truthy object, so the
# is_null() half is silently dropped from the generated SQL.

EXCHANGE = 'Sandbox'
SYMBOL = 'BTC-USD'
START = jh.date_to_timestamp('2023-01-01')
MINUTES = 10
FINISH = START + (MINUTES - 1) * 60_000

# Mirrors the model, except that timeframe stays nullable the way it is for rows written
# before jesse always set it — those are exactly the rows the is_null() branch is for.
LEGACY_SCHEMA = """
    CREATE TABLE candle (
        id TEXT NOT NULL PRIMARY KEY,
        timestamp BIGINT NOT NULL,
        open REAL NOT NULL,
        close REAL NOT NULL,
        high REAL NOT NULL,
        low REAL NOT NULL,
        volume REAL NOT NULL,
        exchange VARCHAR(255) NOT NULL,
        symbol VARCHAR(255) NOT NULL,
        timeframe VARCHAR(255)
    )
"""


def _candle_row(timestamp: int, timeframe) -> dict:
    return {
        'id': jh.generate_unique_id(),
        'timestamp': timestamp,
        'open': 100,
        'close': 110,
        'high': 120,
        'low': 90,
        'volume': 1000,
        'exchange': EXCHANGE,
        'symbol': SYMBOL,
        'timeframe': timeframe,
    }


@pytest.fixture
def sqlite_candles():
    """Binds the Candle model to a throwaway in-memory database for the test."""
    db = peewee.SqliteDatabase(':memory:')
    with db.bind_ctx([Candle]):
        db.execute_sql(LEGACY_SCHEMA)
        yield db


def _store(rows) -> None:
    Candle.insert_many(rows).execute()


def test_null_timeframe_candles_are_returned(sqlite_candles):
    """Legacy candles with a NULL timeframe must still be loaded for backtests."""
    _store([_candle_row(START + i * 60_000, None) for i in range(MINUTES)])

    candles = candle_service._get_candles_from_db(EXCHANGE, SYMBOL, START, FINISH)

    assert len(candles) == MINUTES
    assert candles[0][0] == START
    assert candles[-1][0] == FINISH


def test_one_minute_candles_are_returned(sqlite_candles):
    _store([_candle_row(START + i * 60_000, '1m') for i in range(MINUTES)])

    candles = candle_service._get_candles_from_db(EXCHANGE, SYMBOL, START, FINISH)

    assert len(candles) == MINUTES


def test_higher_timeframe_candles_are_excluded(sqlite_candles):
    """Only 1m (or untimeframed) rows may be used as the source candles."""
    _store([_candle_row(START + i * 60_000, '1m') for i in range(MINUTES)])
    _store([_candle_row(START + i * 60_000, '5m') for i in range(MINUTES)])

    candles = candle_service._get_candles_from_db(EXCHANGE, SYMBOL, START, FINISH)

    assert len(candles) == MINUTES


def test_sparse_warmup_loads_completed_clock_buckets(sqlite_candles):
    trading_start = START + 20 * 60_000
    observed_minutes = [0, 7, 10, 14, 17]
    _store([
        _candle_row(START + minute * 60_000, '1m')
        for minute in observed_minutes
    ])

    candles = candle_service._get_observed_warmup_candles_from_db(
        EXCHANGE,
        SYMBOL,
        trading_start,
        candle_count=2,
        timeframe='5m',
    )

    assert candles[:, 0].tolist() == [
        START + 10 * 60_000,
        START + 14 * 60_000,
        START + 17 * 60_000,
    ]


def test_sparse_warmup_reports_missing_completed_buckets(sqlite_candles):
    _store([_candle_row(START, '1m')])

    with pytest.raises(
        candle_service.CandleNotFoundInDatabase,
        match='Only 1 of 2 required completed 5m warmup candles',
    ):
        candle_service._get_observed_warmup_candles_from_db(
            EXCHANGE,
            SYMBOL,
            START + 10 * 60_000,
            candle_count=2,
            timeframe='5m',
        )


def test_python_or_would_drop_the_is_null_branch():
    """Pins down *why* the condition must use `|` rather than `or`."""
    correct = (Candle.timeframe == '1m') | (Candle.timeframe.is_null())
    buggy = Candle.timeframe == '1m' or Candle.timeframe.is_null()

    correct_sql, _ = Candle.select().where(correct).sql()
    buggy_sql, _ = Candle.select().where(buggy).sql()
    only_left_sql, _ = Candle.select().where(Candle.timeframe == '1m').sql()

    # `or` short-circuits on the truthy left operand, so the NULL check disappears
    assert buggy_sql == only_left_sql
    # while `|` keeps both branches in the generated SQL
    assert correct_sql != only_left_sql
    assert ' OR ' in correct_sql.upper()
