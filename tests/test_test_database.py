import pytest

from jesse.models.BacktestSession import BacktestSession
from jesse.models.Candle import Candle
from jesse.services import test_database
from jesse.services.db import postgres_schema


def configure_test_environment(monkeypatch, schema: str = 'e2e_dashboard') -> None:
    values = {
        'IS_TEST_ENV': 'TRUE',
        'RESET_TEST_DATABASE': 'TRUE',
        'POSTGRES_SCHEMA': schema,
        'POSTGRES_NAME': 'jesse_db',
        'POSTGRES_USERNAME': 'jesse_user',
        'POSTGRES_PASSWORD': 'password',
        'POSTGRES_HOST': '127.0.0.1',
        'POSTGRES_PORT': '5432',
    }
    monkeypatch.setattr(test_database, 'ENV_VALUES', values)
    monkeypatch.setattr('jesse.services.db.ENV_VALUES', values)
    monkeypatch.setattr(test_database, 'is_test_env', lambda: True)


@pytest.mark.parametrize('schema', [
    'e2e_dashboard',
    'dashboard_test',
    'testing_dashboard_2',
])
def test_accepts_explicit_test_schema_names(monkeypatch, schema):
    configure_test_environment(monkeypatch, schema)

    assert test_database.assert_safe_test_database() == schema


@pytest.mark.parametrize('schema', [
    'public',
    'dashboard',
    'e2e-dashboard',
    'test;drop_schema',
])
def test_rejects_unsafe_test_schema_names(monkeypatch, schema):
    configure_test_environment(monkeypatch, schema)

    with pytest.raises((RuntimeError, ValueError)):
        test_database.assert_safe_test_database()


def test_rejects_test_database_operations_outside_test_environment(monkeypatch):
    configure_test_environment(monkeypatch)
    monkeypatch.setattr(test_database, 'is_test_env', lambda: False)

    with pytest.raises(RuntimeError, match='IS_TEST_ENV=TRUE'):
        test_database.assert_safe_test_database()


def test_postgres_schema_defaults_to_public(monkeypatch):
    monkeypatch.setattr('jesse.services.db.ENV_VALUES', {})

    assert postgres_schema() == 'public'


def test_database_reset_is_opt_in(monkeypatch):
    configure_test_environment(monkeypatch)
    test_database.ENV_VALUES['RESET_TEST_DATABASE'] = 'FALSE'

    assert test_database.reset_test_database_if_requested() is False


def test_database_reset_drops_and_recreates_only_the_validated_schema(monkeypatch):
    configure_test_environment(monkeypatch)
    statements = []

    class FakeConnection:
        def __init__(self, name, **kwargs):
            assert name == 'jesse_db'
            assert kwargs['user'] == 'jesse_user'

        def connect(self):
            pass

        def execute_sql(self, statement):
            statements.append(statement)

        def close(self):
            pass

    monkeypatch.setattr(test_database, 'PostgresqlExtDatabase', FakeConnection)
    monkeypatch.setattr(test_database.database, 'close_connection', lambda: None)

    assert test_database.reset_test_database_if_requested() is True
    assert statements == [
        'DROP SCHEMA IF EXISTS "e2e_dashboard" CASCADE',
        'CREATE SCHEMA "e2e_dashboard"',
    ]


def test_data_reset_truncates_every_table_in_the_test_schema(monkeypatch):
    configure_test_environment(monkeypatch)
    statements = []

    class FakeDatabase:
        def get_tables(self, schema=None):
            assert schema == 'e2e_dashboard'
            return ['backtestsession', 'candle']

        def execute_sql(self, statement):
            statements.append(statement)

    monkeypatch.setattr(test_database.database, 'db', FakeDatabase())
    monkeypatch.setattr(test_database.database, 'open_connection', lambda: None)

    assert test_database.reset_test_data() == 2
    assert statements == [
        'TRUNCATE TABLE "e2e_dashboard"."backtestsession", '
        '"e2e_dashboard"."candle" RESTART IDENTITY CASCADE'
    ]


def test_data_reset_ignores_table_names_that_cannot_be_quoted_safely(monkeypatch):
    configure_test_environment(monkeypatch)
    statements = []

    class FakeDatabase:
        def get_tables(self, schema=None):
            assert schema == 'e2e_dashboard'
            return ['candle', 'candle"; DROP SCHEMA public; --']

        def execute_sql(self, statement):
            statements.append(statement)

    monkeypatch.setattr(test_database.database, 'db', FakeDatabase())
    monkeypatch.setattr(test_database.database, 'open_connection', lambda: None)

    assert test_database.reset_test_data() == 1
    assert statements == [
        'TRUNCATE TABLE "e2e_dashboard"."candle" RESTART IDENTITY CASCADE'
    ]


def test_seed_test_data_serializes_sessions_and_creates_candles(monkeypatch):
    configure_test_environment(monkeypatch)
    created_sessions = []
    created_candles = []
    monkeypatch.setattr(
        BacktestSession,
        'create',
        lambda **values: created_sessions.append(values),
    )
    monkeypatch.setattr(
        Candle,
        'create',
        lambda **values: created_candles.append(values),
    )

    counts = test_database.seed_test_data({
        'backtest_sessions': [{
            'id': '00000000-0000-4000-8000-000000000001',
            'status': 'finished',
            'metrics': {'net_profit_percentage': 12.5},
            'trades': [{'strategy_name': 'E2EStrategy'}],
            'state': {'form': {'strategy': 'E2EStrategy'}},
            'created_at': 1_780_315_200_000,
            'updated_at': 1_780_315_200_000,
        }],
        'candles': [{
            'timestamp': 1_780_315_200_000,
            'open': 70_000,
            'close': 70_100,
            'high': 70_200,
            'low': 69_900,
            'volume': 10,
            'exchange': 'Binance Perpetual Futures',
            'symbol': 'BTC-USDT',
        }],
    })

    assert counts == {'backtest_sessions': 1, 'candles': 1}
    assert created_sessions[0]['metrics'] == '{"net_profit_percentage": 12.5}'
    assert created_sessions[0]['trades'] == '[{"strategy_name": "E2EStrategy"}]'
    assert created_sessions[0]['state'] == '{"form": {"strategy": "E2EStrategy"}}'
    assert created_candles[0]['timeframe'] == '1m'
    assert created_candles[0]['id']


def test_seed_test_data_supports_empty_payload(monkeypatch):
    configure_test_environment(monkeypatch)
    monkeypatch.setattr(BacktestSession, 'create', lambda **values: pytest.fail(str(values)))
    monkeypatch.setattr(Candle, 'create', lambda **values: pytest.fail(str(values)))

    assert test_database.seed_test_data({}) == {
        'backtest_sessions': 0,
        'candles': 0,
    }
