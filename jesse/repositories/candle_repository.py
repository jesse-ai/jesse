from jesse.models.Candle import Candle
import jesse.helpers as jh
from collections.abc import Sequence
from collections.abc import Iterator
from typing import List, TYPE_CHECKING
from uuid import uuid4
import numpy as np
import arrow
import peewee

if TYPE_CHECKING:
    from jesse.services.historical_data.contracts import HistoricalCandle


# Nine values are bound per row; 5,000 remains below PostgreSQL's 65,535 bind-parameter limit.
OBSERVED_CANDLE_INSERT_BATCH_SIZE = 5_000
# Server-side cursor batches keep large CSV exports bounded without holding every row in Python.
CANDLE_EXPORT_BATCH_SIZE = 5_000


def delete_candles_from_db(exchange: str, symbol: str) -> int:
    """
    Deletes all candles (every stored timeframe) for the given exchange and symbol and
    returns the number of deleted rows.
    """
    return Candle.delete().where(
        Candle.exchange == exchange,
        Candle.symbol == symbol
    ).execute()


class CandlesAlreadyExist(Exception):
    """The target exchange and symbol already hold candles; refuse to mix two series."""


# Each chunk is one server-side INSERT ... SELECT that commits on its own, so a multi-year series
# copies in seconds and never holds a long table lock (new Jesse processes take one on startup).
COPY_CANDLES_BATCH_SIZE = 100_000


def _new_candle_id_sql() -> peewee.SQL:
    """
    A fresh UUID expression for the bound database.

    PostgreSQL gets a time-ordered id (microsecond clock prefix, random suffix) instead of a
    random v4: on a candle table with over a hundred million rows, random keys scatter every
    insert across the primary-key index and run about 25x slower than appending in order.
    """
    if isinstance(Candle._meta.database, peewee.PostgresqlDatabase):
        return peewee.SQL(
            "(lpad(to_hex((extract(epoch from clock_timestamp()) * 1000000)::bigint), 16, '0')"
            " || substr(md5(random()::text), 1, 16))::uuid"
        )
    return peewee.SQL(
        "lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-4' || substr(hex(randomblob(2)), 2)"
        " || '-' || substr('89ab', abs(random()) % 4 + 1, 1) || substr(hex(randomblob(2)), 2)"
        " || '-' || hex(randomblob(6)))"
    )


def copy_candles(
    exchange: str,
    symbol: str,
    target_exchange: str,
    target_symbol: str,
    delete_source: bool = False,
) -> dict:
    """
    Duplicate every stored candle (all timeframes) of one exchange/symbol under another
    exchange and/or symbol so backtests can select the same data as a different market.

    Refuses to copy onto itself or onto a target that already has candles, so no two
    series are ever merged. With `delete_source=True` the original rows are removed once
    the copy is complete, which turns the copy into a rename. Chunks commit individually:
    if a copy is interrupted, delete the partial target before retrying.
    """
    if (target_exchange, target_symbol) == (exchange, symbol):
        raise ValueError('The target must differ from the source exchange or symbol')

    source_filter = (Candle.exchange == exchange) & (Candle.symbol == symbol)
    target_filter = (Candle.exchange == target_exchange) & (Candle.symbol == target_symbol)
    if not Candle.select(Candle.id).where(source_filter).limit(1).exists():
        raise ValueError(f'No candles are stored for {symbol} on {exchange}')
    if Candle.select(Candle.id).where(target_filter).limit(1).exists():
        raise CandlesAlreadyExist(
            f'{target_symbol} on {target_exchange} already has candles; delete them first'
        )

    copied = 0
    timeframes = [
        timeframe
        for (timeframe,) in Candle.select(Candle.timeframe).where(source_filter).distinct().tuples()
    ]
    insert_fields = [
        Candle.id, Candle.timestamp, Candle.open, Candle.close, Candle.high, Candle.low, Candle.volume,
        Candle.exchange, Candle.symbol, Candle.timeframe,
    ]
    for timeframe in timeframes:
        timeframe_filter = source_filter & (
            Candle.timeframe.is_null() if timeframe is None else (Candle.timeframe == timeframe)
        )
        last_timestamp = None
        while True:
            chunk_filter = timeframe_filter
            if last_timestamp is not None:
                chunk_filter &= Candle.timestamp > last_timestamp
            # Keyset boundaries keep every statement bounded regardless of the series length.
            boundary = (
                Candle.select(Candle.timestamp)
                .where(chunk_filter)
                .order_by(Candle.timestamp)
                .limit(1)
                .offset(COPY_CANDLES_BATCH_SIZE - 1)
                .scalar()
            )
            if boundary is not None:
                chunk_filter &= Candle.timestamp <= boundary
                chunk_size = COPY_CANDLES_BATCH_SIZE
            else:
                # Only the final chunk needs counting; every earlier one is exactly one batch.
                chunk_size = Candle.select().where(chunk_filter).count()
            # Drivers disagree on what an INSERT ... SELECT returns, so the count comes from the keyset.
            Candle.insert_from(
                Candle.select(
                    _new_candle_id_sql(), Candle.timestamp, Candle.open, Candle.close, Candle.high,
                    Candle.low, Candle.volume, peewee.Value(target_exchange), peewee.Value(target_symbol),
                    Candle.timeframe,
                ).where(chunk_filter),
                insert_fields,
            ).execute()
            copied += chunk_size
            if boundary is None:
                break
            last_timestamp = boundary
    deleted = Candle.delete().where(source_filter).execute() if delete_source else 0
    return {'copied': copied, 'deleted': deleted}


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
    # One grouped scan avoids two additional database round trips for every stored dataset.
    summaries = (
        Candle.select(
            Candle.exchange,
            Candle.symbol,
            peewee.fn.MIN(Candle.timestamp),
            peewee.fn.MAX(Candle.timestamp),
        )
        .group_by(Candle.exchange, Candle.symbol)
        .tuples()
    )
    return [
        {
            'exchange': exchange,
            'symbol': symbol,
            'start_date': arrow.get(first_timestamp / 1000).format('YYYY-MM-DD'),
            'end_date': arrow.get(last_timestamp / 1000).format('YYYY-MM-DD'),
        }
        for exchange, symbol, first_timestamp, last_timestamp in summaries
    ]


def get_stored_symbols(exchange: str) -> list[str]:
    """Return the sorted symbols currently persisted for one historical source."""
    return [
        symbol
        for (symbol,) in (
            Candle.select(Candle.symbol)
            .where(Candle.exchange == exchange)
            .distinct()
            .order_by(Candle.symbol.asc())
            .tuples()
        )
    ]


def stream_one_minute_candles(
    exchange: str,
    symbol: str,
) -> Iterator[list[tuple[int, float, float, float, float, float]]]:
    """Yield an ordered canonical candle series through a PostgreSQL server-side cursor."""
    timeframe_condition = (Candle.timeframe == '1m') | Candle.timeframe.is_null()
    query = (
        Candle.select(
            Candle.timestamp,
            Candle.open,
            Candle.close,
            Candle.high,
            Candle.low,
            Candle.volume,
        )
        .where(
            Candle.exchange == exchange,
            Candle.symbol == symbol,
            timeframe_condition,
        )
        .order_by(Candle.timestamp.asc())
    )
    sql, params = query.sql()
    db = Candle._meta.database
    opened_here = db.is_closed()
    db.connect(reuse_if_open=True)
    try:
        # Named cursors fetch incrementally and require a transaction for their full lifetime.
        with db.atomic(), db.connection().cursor(name=f'candle_export_{uuid4().hex}') as cursor:
            cursor.itersize = CANDLE_EXPORT_BATCH_SIZE
            cursor.execute(sql, params)
            while rows := cursor.fetchmany(CANDLE_EXPORT_BATCH_SIZE):
                yield rows
    finally:
        if opened_here and not db.is_closed():
            db.close()


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


def get_candle_timestamp_bounds(exchange: str, symbol: str, timeframe: str) -> tuple[int | None, int | None]:
    """Return the first and latest stored timestamps for one canonical candle series."""
    timeframe_condition = Candle.timeframe == timeframe
    if timeframe == '1m':
        # Older imports may have stored one-minute rows before the timeframe column was populated.
        timeframe_condition = timeframe_condition | Candle.timeframe.is_null()
    first_timestamp, last_timestamp = (
        Candle.select(
            peewee.fn.MIN(Candle.timestamp),
            peewee.fn.MAX(Candle.timestamp),
        )
        .where(
            Candle.exchange == exchange,
            Candle.symbol == symbol,
            timeframe_condition,
        )
        .tuples()
        .get()
    )
    return (
        int(first_timestamp) if first_timestamp is not None else None,
        int(last_timestamp) if last_timestamp is not None else None,
    )


def store_observed_candles(
    exchange: str,
    symbol: str,
    timeframe: str,
    candles: Sequence['HistoricalCandle'],
) -> None:
    """Persist one provider page atomically while retaining existing canonical rows."""
    # SQL batching respects PostgreSQL's bind limit; the outer transaction preserves resumable boundaries.
    with Candle._meta.database.atomic():
        for offset in range(0, len(candles), OBSERVED_CANDLE_INSERT_BATCH_SIZE):
            rows = [
                {
                    'id': jh.generate_unique_id(),
                    'exchange': exchange,
                    'symbol': symbol,
                    'timeframe': timeframe,
                    'timestamp': candle.timestamp,
                    'open': candle.open,
                    'close': candle.close,
                    'high': candle.high,
                    'low': candle.low,
                    'volume': candle.volume,
                }
                for candle in candles[offset:offset + OBSERVED_CANDLE_INSERT_BATCH_SIZE]
            ]
            Candle.insert_many(rows).on_conflict_ignore().execute()


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
