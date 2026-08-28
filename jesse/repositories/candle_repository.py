from jesse.models.Candle import Candle
import jesse.helpers as jh
from typing import List
import numpy as np
import arrow


def delete_candles_from_db(exchange: str, symbol: str) -> None:
    """
    Deletes all candles for the given exchange and symbol
    """
    Candle.delete().where(
        Candle.exchange == exchange,
        Candle.symbol == symbol
    ).execute()


def purge_candles_by_exchanges(exchanges: list) -> int:
    """
    Deletes all candles for the given list of exchanges. Returns the number of deleted rows.
    """
    count = Candle.delete().where(Candle.exchange.in_(exchanges)).execute()
    return count


def get_existing_candles() -> List[dict]:
    """
    Returns a list of all existing candles grouped by exchange and symbol
    """
    # Peewee can't express this, so we use raw SQL. A DISTINCT or GROUP BY over
    # the candle table reads every row, which takes minutes on large databases.
    # This recursive CTE emulates an index skip scan (PostgreSQL has no native
    # one before v18): each step jumps straight to the next
    # (exchange, symbol, timeframe) group with a single probe of the compound
    # index, and the first/last timestamps are read with two more index probes
    # per group. When no next group exists the probes return a NULL row, which
    # stops the recursion and is filtered out below. The SQL is portable
    # between PostgreSQL and SQLite (used by the unit tests).
    query = """
        WITH RECURSIVE timeframe_groups (exchange, symbol, timeframe) AS (
            SELECT exchange, symbol, timeframe FROM (
                SELECT exchange, symbol, timeframe
                FROM candle
                ORDER BY exchange, symbol, timeframe
                LIMIT 1
            ) AS first_group
            UNION ALL
            SELECT
                (SELECT c.exchange FROM candle c
                 WHERE (c.exchange, c.symbol, c.timeframe) > (g.exchange, g.symbol, g.timeframe)
                 ORDER BY c.exchange, c.symbol, c.timeframe LIMIT 1),
                (SELECT c.symbol FROM candle c
                 WHERE (c.exchange, c.symbol, c.timeframe) > (g.exchange, g.symbol, g.timeframe)
                 ORDER BY c.exchange, c.symbol, c.timeframe LIMIT 1),
                (SELECT c.timeframe FROM candle c
                 WHERE (c.exchange, c.symbol, c.timeframe) > (g.exchange, g.symbol, g.timeframe)
                 ORDER BY c.exchange, c.symbol, c.timeframe LIMIT 1)
            FROM timeframe_groups g
            WHERE g.exchange IS NOT NULL
        )
        SELECT exchange, symbol, MIN(first_timestamp), MAX(last_timestamp)
        FROM (
            SELECT
                g.exchange,
                g.symbol,
                (SELECT MIN(c."timestamp") FROM candle c
                 WHERE c.exchange = g.exchange AND c.symbol = g.symbol AND c.timeframe = g.timeframe) AS first_timestamp,
                (SELECT MAX(c."timestamp") FROM candle c
                 WHERE c.exchange = g.exchange AND c.symbol = g.symbol AND c.timeframe = g.timeframe) AS last_timestamp
            FROM timeframe_groups g
            WHERE g.exchange IS NOT NULL
        ) AS group_ranges
        GROUP BY exchange, symbol
        ORDER BY exchange, symbol
    """

    # go through the model's database handle so unit tests can rebind it
    cursor = Candle._meta.database.execute_sql(query)

    results = []
    for exchange, symbol, first_timestamp, last_timestamp in cursor.fetchall():
        results.append({
            'exchange': exchange,
            'symbol': symbol,
            'start_date': arrow.get(first_timestamp / 1000).format('YYYY-MM-DD'),
            'end_date': arrow.get(last_timestamp / 1000).format('YYYY-MM-DD')
        })

    return results


def fetch_candles_from_db(exchange: str, symbol: str, timeframe: str, start_date: int, finish_date: int) -> tuple:
    res = tuple(
        Candle.select(
            Candle.timestamp, Candle.open, Candle.close, Candle.high, Candle.low,
            Candle.volume
        ).where(
            Candle.exchange == exchange,
            Candle.symbol == symbol,
            Candle.timeframe == timeframe,
            Candle.timestamp.between(start_date, finish_date)
        ).order_by(Candle.timestamp.asc()).tuples()
    )

    return res


def store_candles_into_db(exchange: str, symbol: str, timeframe: str, candles: np.ndarray, on_conflict='ignore') -> None:
    # make sure the number of candles is more than 0
    if len(candles) == 0:
        raise Exception(f'No candles to store for {exchange}-{symbol}-{timeframe}')

    # convert candles to list of dicts
    candles_list = []
    for candle in candles:
        d = {
            'id': jh.generate_unique_id(),
            'symbol': symbol,
            'exchange': exchange,
            'timestamp': candle[0],
            'open': candle[1],
            'high': candle[3],
            'low': candle[4],
            'close': candle[2],
            'volume': candle[5],
            'timeframe': timeframe,
        }
        candles_list.append(d)

    if on_conflict == 'ignore':
        Candle.insert_many(candles_list).on_conflict_ignore().execute()
    elif on_conflict == 'replace':
        Candle.insert_many(candles_list).on_conflict(
            conflict_target=['exchange', 'symbol', 'timeframe', 'timestamp'],
            preserve=(Candle.open, Candle.high, Candle.low, Candle.close, Candle.volume),
        ).execute()
    elif on_conflict == 'error':
        Candle.insert_many(candles_list).execute()
    else:
        raise Exception(f'Unknown on_conflict value: {on_conflict}')


def store_candle_into_db(exchange: str, symbol: str, timeframe: str, candle: np.ndarray, on_conflict='ignore') -> None:
    d = {
        'id': jh.generate_unique_id(),
        'exchange': exchange,
        'symbol': symbol,
        'timeframe': timeframe,
        'timestamp': candle[0],
        'open': candle[1],
        'high': candle[3],
        'low': candle[4],
        'close': candle[2],
        'volume': candle[5]
    }

    if on_conflict == 'ignore':
        Candle.insert(**d).on_conflict_ignore().execute()
    elif on_conflict == 'replace':
        Candle.insert(**d).on_conflict(
            conflict_target=['exchange', 'symbol', 'timeframe', 'timestamp'],
            preserve=(Candle.open, Candle.high, Candle.low, Candle.close, Candle.volume),
        ).execute()
    elif on_conflict == 'error':
        Candle.insert(**d).execute()
    else:
        raise Exception(f'Unknown on_conflict value: {on_conflict}')
