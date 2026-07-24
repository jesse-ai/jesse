import json
import re
from uuid import uuid4

from playhouse.postgres_ext import PostgresqlExtDatabase

from jesse.services.db import database, postgres_schema
from jesse.services.env import ENV_VALUES, is_test_env


def assert_safe_test_database() -> str:
    """Return the schema only when the environment is safe for destructive test operations."""
    if not is_test_env():
        raise RuntimeError('Test database operations require IS_TEST_ENV=TRUE')

    # Destructive helpers are allowed only for unmistakably test-only schemas.
    schema = postgres_schema()
    parts = set(schema.lower().split('_'))
    if schema.lower() == 'public' or not parts.intersection({'e2e', 'test', 'testing'}):
        raise RuntimeError(
            'POSTGRES_SCHEMA must be a non-public schema containing e2e, test, or testing'
        )
    return schema


def _connection_kwargs() -> dict:
    """Build the shared PostgreSQL connection settings from Jesse's environment."""
    return {
        'user': ENV_VALUES['POSTGRES_USERNAME'],
        'password': ENV_VALUES['POSTGRES_PASSWORD'],
        'host': ENV_VALUES['POSTGRES_HOST'],
        'port': int(ENV_VALUES['POSTGRES_PORT']),
        'sslmode': ENV_VALUES.get('POSTGRES_SSLMODE', 'disable'),
    }


def reset_test_database_if_requested() -> bool:
    """Drop and recreate the test schema when RESET_TEST_DATABASE is enabled."""
    if str(ENV_VALUES.get('RESET_TEST_DATABASE') or '').upper() != 'TRUE':
        return False

    schema = assert_safe_test_database()
    database.close_connection()
    # Use a short-lived connection because this operation replaces the whole schema.
    connection = PostgresqlExtDatabase(
        ENV_VALUES['POSTGRES_NAME'],
        **_connection_kwargs(),
    )
    connection.connect()
    try:
        connection.execute_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        connection.execute_sql(f'CREATE SCHEMA "{schema}"')
    finally:
        connection.close()
    return True


def reset_test_data() -> int:
    """Empty every table in the test schema and return the number of tables reset."""
    schema = assert_safe_test_database()
    database.open_connection()
    tables = database.db.get_tables(schema=schema)
    # SQL parameters cannot represent identifiers, so validate names before quoting them.
    safe_tables = [
        table for table in tables
        if re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_]*', table)
    ]
    if safe_tables:
        targets = ', '.join(f'"{schema}"."{table}"' for table in safe_tables)
        database.db.execute_sql(f'TRUNCATE TABLE {targets} RESTART IDENTITY CASCADE')
    return len(safe_tables)


def seed_test_data(payload: dict) -> dict:
    """Insert backtest sessions and candles supplied by the E2E test payload."""
    assert_safe_test_database()
    from jesse.models.BacktestSession import BacktestSession
    from jesse.models.Candle import Candle

    sessions = payload.get('backtest_sessions') or []
    candles = payload.get('candles') or []

    # These model fields store JSON text; keep missing values as SQL NULL.
    for session in sessions:
        BacktestSession.create(
            id=session['id'],
            status=session.get('status', 'finished'),
            metrics=json.dumps(session.get('metrics')) if session.get('metrics') is not None else None,
            equity_curve=json.dumps(session.get('equity_curve')) if session.get('equity_curve') is not None else None,
            trades=json.dumps(session.get('trades')) if session.get('trades') is not None else None,
            hyperparameters=json.dumps(session.get('hyperparameters')) if session.get('hyperparameters') is not None else None,
            chart_data=json.dumps(session.get('chart_data')) if session.get('chart_data') is not None else None,
            state=json.dumps(session.get('state')) if session.get('state') is not None else None,
            title=session.get('title'),
            description=session.get('description'),
            strategy_codes=json.dumps(session.get('strategy_codes')) if session.get('strategy_codes') is not None else None,
            exception=session.get('exception'),
            traceback=session.get('traceback'),
            execution_duration=session.get('execution_duration'),
            created_at=session['created_at'],
            updated_at=session['updated_at'],
        )

    for candle in candles:
        Candle.create(
            id=candle.get('id') or str(uuid4()),
            timestamp=candle['timestamp'],
            open=candle['open'],
            close=candle['close'],
            high=candle['high'],
            low=candle['low'],
            volume=candle['volume'],
            exchange=candle['exchange'],
            symbol=candle['symbol'],
            timeframe=candle.get('timeframe', '1m'),
        )

    return {
        'backtest_sessions': len(sessions),
        'candles': len(candles),
    }
