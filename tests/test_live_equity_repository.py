import numpy as np
import pytest

from jesse.repositories import live_equity_repository


class _FakePeeweeDb:
    def __init__(self, fail_first: bool = False):
        self.calls = []
        self.rollbacks = 0
        self._fail_first = fail_first

    def execute_sql(self, query, params):
        self.calls.append((query, params))
        if self._fail_first and len(self.calls) == 1:
            raise Exception('schema "np" does not exist')

    def rollback(self):
        self.rollbacks += 1


class _FakeDatabaseService:
    def __init__(self, db):
        self.db = db
        self._open = True

    def is_open(self):
        return self._open

    def open_connection(self):
        self._open = True


@pytest.fixture
def repo(monkeypatch):
    # upsert_snapshot() early-returns under pytest unless unit-testing mode is off
    monkeypatch.setattr(live_equity_repository.jh, 'is_unit_testing', lambda: False)
    return live_equity_repository


def test_upsert_snapshot_casts_numpy_scalars_to_float(repo, monkeypatch):
    # issue #644: with numpy 2, psycopg2 renders np.float64 as
    # np.float64(9998.91) in SQL, which Postgres rejects (schema "np" does not exist)
    fake = _FakePeeweeDb()
    monkeypatch.setattr(repo, 'database', _FakeDatabaseService(fake))

    repo.upsert_snapshot('session-id', 1738870415000, 'USD', np.float64(9998.91))

    assert len(fake.calls) == 1
    _, params = fake.calls[0]
    assert type(params[3]) is float
    assert params[3] == 9998.91


def test_upsert_snapshot_rolls_back_before_schema_fallback(repo, monkeypatch):
    # issue #644 (second part): without a rollback, the failed first INSERT leaves
    # the connection in an aborted transaction and the fallback (and every later
    # write) fails with 25P02
    fake = _FakePeeweeDb(fail_first=True)
    monkeypatch.setattr(repo, 'database', _FakeDatabaseService(fake))

    repo.upsert_snapshot('session-id', 1738870415000, 'USD', 9998.91)

    assert fake.rollbacks == 1
    assert len(fake.calls) == 2
    assert 'bucket_ms' in fake.calls[1][0]
