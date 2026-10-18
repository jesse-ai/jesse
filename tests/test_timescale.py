from contextlib import contextmanager
from types import SimpleNamespace

import peewee
import pytest

from jesse.services import timescale


DROP_KEY = 'ALTER TABLE "public"."candle" DROP CONSTRAINT "candle_pkey"'


class FakeDatabase:
    """Answers the catalog queries timescale.py issues and records every statement."""

    def __init__(self, hypertable: bool, primary_key: tuple | None, extension: bool = True, lock_timeout: bool = False):
        self.hypertable = hypertable
        self.primary_key = primary_key
        self.extension = extension
        self.lock_timeout = lock_timeout
        self.statements: list[str] = []

    def execute_sql(self, sql: str, params=None):
        self.statements.append(sql)
        if sql.startswith('ALTER TABLE') and 'DROP CONSTRAINT' in sql and self.lock_timeout:
            raise peewee.OperationalError('canceling statement due to lock timeout')
        if sql.startswith('SELECT create_hypertable'):
            self.hypertable = True
        return SimpleNamespace(fetchone=lambda: self._row(sql))

    def _row(self, sql: str):
        if 'pg_try_advisory_xact_lock' in sql:
            return (True,)
        if 'e.extversion, n.nspname' in sql:
            return ('2.19.3', 'public') if self.extension else None
        if 'FROM pg_extension' in sql:
            return ('2.19.3',) if self.extension else None
        if 'FROM pg_settings' in sql:
            return (1,)
        if 'timescaledb_information.hypertables' in sql:
            return (True,) if self.hypertable else None
        if 'FROM pg_constraint' in sql:
            return self.primary_key
        if sql == 'SHOW server_version_num':
            return ('170002',)
        return None

    @contextmanager
    def atomic(self):
        yield


@pytest.fixture
def use_database(monkeypatch):
    def bind(fake: FakeDatabase) -> FakeDatabase:
        monkeypatch.setattr(timescale, 'database', SimpleNamespace(db=fake))
        monkeypatch.setattr(timescale, 'postgres_schema', lambda: 'public')
        return fake

    return bind


def test_migration_drops_the_identifier_key_from_an_existing_hypertable(use_database, capsys):
    db = use_database(FakeDatabase(hypertable=True, primary_key=('candle_pkey', ['id', 'timestamp'])))

    timescale.drop_identifier_primary_key()

    assert DROP_KEY in db.statements
    assert 'Dropped the (id, timestamp) primary key' in capsys.readouterr().out


def test_migration_is_silent_once_the_key_is_gone(use_database, capsys):
    db = use_database(FakeDatabase(hypertable=True, primary_key=None))

    timescale.drop_identifier_primary_key()

    assert not [statement for statement in db.statements if statement.startswith('ALTER TABLE')]
    assert capsys.readouterr().out == ''


def test_migration_leaves_an_administrator_defined_key_alone(use_database):
    series_key = ('candle_pkey', ['exchange', 'symbol', 'timeframe', 'timestamp'])
    db = use_database(FakeDatabase(hypertable=True, primary_key=series_key))

    timescale.drop_identifier_primary_key()

    assert not [statement for statement in db.statements if statement.startswith('ALTER TABLE')]


@pytest.mark.parametrize('extension', [True, False])
def test_migration_keeps_the_id_key_on_plain_postgresql(use_database, extension):
    db = use_database(FakeDatabase(hypertable=False, primary_key=('candle_pkey', ['id']), extension=extension))

    timescale.drop_identifier_primary_key()

    assert not [statement for statement in db.statements if statement.startswith('ALTER TABLE')]


def test_migration_yields_to_running_sessions_without_failing_startup(use_database, capsys):
    use_database(FakeDatabase(hypertable=True, primary_key=('candle_pkey', ['id', 'timestamp']), lock_timeout=True))

    timescale.drop_identifier_primary_key()

    output = capsys.readouterr().out
    assert 'skipped' in output and 'lock timeout' in output
    assert 'Dropped' not in output


def test_conversion_leaves_only_the_series_key_unique(use_database):
    # A unique key on the UUID makes TimescaleDB decompress every series sharing an inserted timestamp.
    db = use_database(FakeDatabase(hypertable=False, primary_key=('candle_pkey', ['id'])))

    timescale.enable(migrate_existing=True)

    assert DROP_KEY in db.statements
    assert not [statement for statement in db.statements if 'PRIMARY KEY' in statement]
    assert db.statements.index(DROP_KEY) < next(
        index for index, statement in enumerate(db.statements) if statement.startswith('SELECT create_hypertable')
    )
