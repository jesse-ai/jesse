"""Opt-in candle storage tuning; ordinary PostgreSQL queries remain unchanged."""

import re

import peewee

from jesse.services.db import database, postgres_schema
from jesse.services.env import ENV_VALUES

# Weekly chunks balance pruning against chunk overhead. Keep a full month in row
# storage so live updates and recent imports do not routinely decompress history.
CHUNK_MS = 7 * 24 * 60 * 60 * 1000
COMPRESS_AFTER_MS = 30 * 24 * 60 * 60 * 1000


def _identifier(value: str) -> str:
    """Quote names obtained from configuration or PostgreSQL catalogs."""
    return '"' + value.replace('"', '""') + '"'


def _require_loader() -> None:
    """Check a loader-registered setting before executing extension functions."""
    # CREATE EXTENSION without the preloaded library can terminate the PostgreSQL
    # connection, so check registered settings without loading extension code.
    loaded = database.db.execute_sql(
        "SELECT 1 FROM pg_settings WHERE name = 'timescaledb.max_background_workers'"
    ).fetchone()
    if not loaded:
        raise ValueError(
            'TimescaleDB must be loaded in shared_preload_libraries; '
            'configure and restart PostgreSQL before enabling it.'
        )


def _primary_key(table: str) -> tuple | None:
    """Return the candle primary key's constraint name and ordered column names."""
    return database.db.execute_sql(
        'SELECT c.conname, array_agg(a.attname ORDER BY k.ordinality) '
        'FROM pg_constraint c CROSS JOIN LATERAL unnest(c.conkey) '
        'WITH ORDINALITY k(attnum, ordinality) '
        'JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum '
        "WHERE c.conrelid = %s::regclass AND c.contype = 'p' GROUP BY c.conname",
        (table,),
    ).fetchone()


def status() -> dict:
    """Describe storage without installing an extension or modifying tables."""
    db = database.db
    extension = db.execute_sql(
        "SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'"
    ).fetchone()
    result = {'extension_version': extension[0] if extension else None, 'hypertable': False}
    if extension:
        _require_loader()
        row = db.execute_sql(
            'SELECT compression_enabled FROM timescaledb_information.hypertables '
            'WHERE hypertable_schema = %s AND hypertable_name = %s',
            (postgres_schema(), 'candle'),
        ).fetchone()
        result.update(hypertable=row is not None, compression=bool(row and row[0]))
    return result


def enable(*, migrate_existing: bool, compression: bool = True) -> str:
    """Convert candle storage atomically; only explicit maintenance moves history.

    A missing server extension is a supported PostgreSQL fallback. SQL or permission
    failures roll back the whole conversion, including the primary-key change.
    """
    db = database.db
    schema = postgres_schema()
    table = f'{_identifier(schema)}."candle"'
    with db.atomic():
        # Serialize setup in this database/schema without waiting on another owner.
        locked = db.execute_sql(
            'SELECT pg_try_advisory_xact_lock(hashtext(%s), hashtext(%s))',
            ('jesse-timescale', schema),
        ).fetchone()[0]
        if not locked:
            raise ValueError('Another TimescaleDB setup is running for this schema')
        # Fail quickly on a busy live table; the user can retry during maintenance.
        db.execute_sql("SET LOCAL lock_timeout = '5s'")
        extension = db.execute_sql(
            "SELECT e.extversion, n.nspname FROM pg_extension e "
            "JOIN pg_namespace n ON n.oid = e.extnamespace WHERE e.extname = 'timescaledb'"
        ).fetchone()
        if not migrate_existing:
            if extension and status()['hypertable']:
                # Startup must preserve an administrator's partition-only setup
                # and existing compression policy rather than reconfigure it.
                return 'TimescaleDB candle storage is already configured; keeping its existing settings.'
            if db.execute_sql(f'SELECT 1 FROM {table} LIMIT 1').fetchone():
                # Avoid extension installation and exclusive locks for existing
                # history; recheck under the conversion lock if it looks empty.
                return 'Existing candles need maintenance: stop sessions and run jesse enable-timescale.'
        if not extension:
            available = db.execute_sql(
                "SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb'"
            ).fetchone()
            if not available:
                if migrate_existing:
                    raise ValueError('TimescaleDB is unavailable on this server; install and configure the extension first.')
                return 'TimescaleDB is unavailable on this server; continuing with PostgreSQL.'
            _require_loader()
            # The extension belongs to the database, not to a disposable project
            # schema that might be dropped while other projects still use it.
            db.execute_sql('CREATE EXTENSION IF NOT EXISTS timescaledb WITH SCHEMA public')
            extension = db.execute_sql(
                "SELECT e.extversion, n.nspname FROM pg_extension e "
                "JOIN pg_namespace n ON n.oid = e.extnamespace WHERE e.extname = 'timescaledb'"
            ).fetchone()
        version = re.match(r'(\d+)\.(\d+)', extension[0])
        if compression and (not version or tuple(map(int, version.groups())) < (2, 11)):
            raise ValueError('Candle compression requires TimescaleDB 2.11+ for historical updates')
        if compression and int(db.execute_sql('SHOW server_version_num').fetchone()[0]) < 140000:
            raise ValueError('Candle compression requires PostgreSQL 14+')
        # Jesse schemas deliberately exclude public; resolve extension functions
        # explicitly within this transaction without changing normal query routing.
        db.execute_sql(f'SET LOCAL search_path TO {_identifier(schema)}, {_identifier(extension[1])}, pg_catalog')
        current = status()
        if not current['hypertable']:
            # Hold the conversion lock before checking emptiness: another process
            # must not insert history between the startup check and migration.
            db.execute_sql(f'LOCK TABLE {table} IN ACCESS EXCLUSIVE MODE')
            if not migrate_existing and db.execute_sql(f'SELECT 1 FROM {table} LIMIT 1').fetchone():
                # A writer won the race after the preflight read. Roll back any
                # extension installation as well as abandoning the conversion.
                raise ValueError('Existing candles need maintenance: stop sessions and run jesse enable-timescale.')
            # Timescale requires the partition timestamp in every unique index, and
            # checks each of them against compressed history. A key on the UUID
            # would decompress every series sharing an inserted timestamp, so the
            # venue/symbol/timeframe/time index stays the only uniqueness rule.
            primary = _primary_key(table)
            if primary and primary[1] == ['id']:
                # No CASCADE: custom dependent foreign keys must block conversion,
                # rather than silently breaking a customer's schema.
                db.execute_sql(f'ALTER TABLE {table} DROP CONSTRAINT {_identifier(primary[0])}')
            db.execute_sql(
                "SELECT create_hypertable(%s::regclass, 'timestamp', "
                'chunk_time_interval => %s::bigint, migrate_data => true, if_not_exists => true)',
                (table, CHUNK_MS),
            )
        if compression and not current.get('compression', False):
            db.execute_sql(
                f'ALTER TABLE {table} SET (timescaledb.compress = true, '
                "timescaledb.compress_segmentby = 'exchange,symbol,timeframe', "
                "timescaledb.compress_orderby = 'timestamp DESC')"
            )
        if compression:
            now_function = f'{_identifier(schema)}."jesse_candle_now_ms"'
            # Candle timestamps are integer milliseconds, so compression policies
            # need an integer clock with the same unit rather than SQL timestamps.
            db.execute_sql(
                f'CREATE OR REPLACE FUNCTION {now_function}() RETURNS bigint '
                "LANGUAGE SQL STABLE AS 'SELECT floor(extract(epoch FROM now()) * 1000)::bigint'"
            )
            db.execute_sql('SELECT set_integer_now_func(%s::regclass, %s::regproc, replace_if_exists => true)', (table, now_function))
            db.execute_sql('SELECT add_compression_policy(%s::regclass, %s::bigint, if_not_exists => true)', (table, COMPRESS_AFTER_MS))
    return 'TimescaleDB candle storage enabled' + ('; history older than 30 days compresses automatically.' if compression else '.')


def drop_identifier_primary_key() -> None:
    """Remove the (id, timestamp) primary key that earlier conversions left on the hypertable.

    The UUID is not a compression segment, so TimescaleDB could only check that key by
    decompressing every series sharing an inserted timestamp. Historical imports then
    unpacked unrelated symbols and large ones exceeded the decompression limit.
    """
    db = database.db
    try:
        if not status()['hypertable']:
            return
        table = f'{_identifier(postgres_schema())}."candle"'
        with db.atomic():
            # Every chunk is locked; yield to running sessions and retry at the next start.
            db.execute_sql("SET LOCAL lock_timeout = '5s'")
            primary = _primary_key(table)
            # A key the administrator defined differently is not Jesse's to remove.
            if not primary or primary[1] != ['id', 'timestamp']:
                return
            # No CASCADE: custom dependent foreign keys must block the change.
            db.execute_sql(f'ALTER TABLE {table} DROP CONSTRAINT {_identifier(primary[0])}')
    except (peewee.PeeweeException, ValueError) as exc:
        # Candle storage keeps working with the old key, so startup continues.
        print(f'Candle primary key migration skipped, retrying at the next start: {exc}')
        return
    print('Dropped the (id, timestamp) primary key from the TimescaleDB candle table.')


def configure_if_requested() -> None:
    """Apply optional empty-table setup at server startup, never in worker imports."""
    if str(ENV_VALUES.get('TIMESCALEDB_ENABLED', '')).upper() != 'TRUE':
        return
    try:
        message = enable(migrate_existing=False)
    except (peewee.PeeweeException, ValueError) as exc:
        # Optional tuning must not prevent ordinary PostgreSQL startup. Transaction
        # rollback preserves the existing table; converted tables remain Timescale.
        message = f'TimescaleDB setup skipped: {exc}'
    print(message)
