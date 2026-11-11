from types import SimpleNamespace

import numpy as np
import pytest
from psycopg2.extensions import adapt

import jesse.services.db  # noqa: F401  registers the numpy adapters
from jesse.repositories import live_equity_repository


@pytest.mark.parametrize('value, sql', [
    # numpy 2 prints a float64 as `np.float64(9998.91)`, which PostgreSQL reads as a schema
    # called "np" (jesse-ai/jesse#644).
    (np.float64(9998.91), b'9998.91'),
    (np.float32(1.5), b'1.5'),
    (np.int64(5), b'5'),
    (np.uint32(7), b'7'),
    (np.bool_(True), b'true'),
])
def test_numpy_numbers_reach_postgres_as_plain_numbers(value, sql):
    assert adapt(value).getquoted() == sql


@pytest.fixture
def fake_database(monkeypatch):
    calls = SimpleNamespace(executed=[], rollbacks=0, failures=[])

    def execute_sql(query, params):
        calls.executed.append(params)
        if calls.failures:
            raise calls.failures.pop(0)

    def rollback():
        calls.rollbacks += 1

    db = SimpleNamespace(execute_sql=execute_sql, rollback=rollback)
    monkeypatch.setattr(live_equity_repository.jh, 'is_unit_testing', lambda: False)
    monkeypatch.setattr(live_equity_repository.database, 'db', db)
    monkeypatch.setattr(live_equity_repository.database, 'is_open', lambda: True)
    return calls


def test_a_snapshot_saves_plain_numbers(fake_database):
    live_equity_repository.upsert_snapshot('session', np.int64(60_000), 'USDT', np.float64(9998.91))

    [params] = fake_database.executed
    assert params == ('session', 60_000, 'USDT', 9998.91)
    assert type(params[1]) is int and type(params[3]) is float


def test_a_failed_snapshot_is_rolled_back_so_later_writes_work(fake_database):
    fake_database.failures = [RuntimeError('first'), RuntimeError('fallback')]

    with pytest.raises(RuntimeError, match='fallback'):
        live_equity_repository.upsert_snapshot('session', 60_000, 'USDT', 1.0)

    # One rollback before the fallback query and one after it fails, so the shared
    # connection isn't left in an aborted transaction.
    assert fake_database.rollbacks == 2
