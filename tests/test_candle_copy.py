import json
from hashlib import sha256
from types import SimpleNamespace

import peewee
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import jesse.helpers as jh
import jesse.mcp.tools.services.candles as candles_service
from jesse.controllers import candles_controller
from jesse.models.Candle import Candle
from jesse.repositories import candle_repository
from jesse.services import auth


SOURCE = ('Massive Stocks', 'SPY-USD')
TARGET = ('Binance Perpetual Futures', 'SPY-USDT')
PASSWORD = 'test-password'
AUTHORIZATION = sha256(PASSWORD.encode('utf-8')).hexdigest()


# Mirrors the production table: legacy rows may carry a NULL timeframe, which the copy must preserve.
CANDLE_SCHEMA = """
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


@pytest.fixture
def sqlite_candles():
    """Bind the Candle model to a throwaway in-memory database for the test."""
    db = peewee.SqliteDatabase(':memory:')
    with db.bind_ctx([Candle]):
        db.execute_sql(CANDLE_SCHEMA)
        db.execute_sql('CREATE UNIQUE INDEX candle_series ON candle (exchange, symbol, timeframe, timestamp)')
        yield db


def _row(exchange, symbol, timestamp, timeframe, price=100.0):
    return {
        'id': jh.generate_unique_id(),
        'exchange': exchange,
        'symbol': symbol,
        'timestamp': timestamp,
        'open': price,
        'close': price + 1,
        'high': price + 2,
        'low': price - 1,
        'volume': 10 + timestamp / 60_000,
        'timeframe': timeframe,
    }


def _seed_source(minutes=12, extra_timeframes=('5m', None)):
    rows = [_row(*SOURCE, i * 60_000, '1m', price=100 + i) for i in range(minutes)]
    for timeframe in extra_timeframes:
        rows += [_row(*SOURCE, i * 300_000, timeframe, price=500 + i) for i in range(minutes // 5)]
    Candle.insert_many(rows).execute()
    return rows


def _series(exchange, symbol):
    rows = Candle.select(
        Candle.timeframe, Candle.timestamp, Candle.open, Candle.close, Candle.high, Candle.low, Candle.volume
    ).where((Candle.exchange == exchange) & (Candle.symbol == symbol)).tuples()
    return sorted(rows, key=lambda row: (row[0] or '', row[1]))


def test_copy_candles_duplicates_every_timeframe_with_fresh_ids_and_keeps_the_source(sqlite_candles, monkeypatch):
    monkeypatch.setattr(candle_repository, 'COPY_CANDLES_BATCH_SIZE', 5)
    _seed_source()
    source_before = _series(*SOURCE)
    source_ids = {row.id for row in Candle.select(Candle.id).where(Candle.exchange == SOURCE[0])}

    result = candle_repository.copy_candles(*SOURCE, *TARGET)

    assert result == {'copied': len(source_before), 'deleted': 0}
    assert _series(*TARGET) == source_before
    assert _series(*SOURCE) == source_before
    target_ids = {row.id for row in Candle.select(Candle.id).where(Candle.exchange == TARGET[0])}
    assert target_ids.isdisjoint(source_ids)
    assert len(target_ids) == len(source_before)


def test_copy_candles_can_move_the_series(sqlite_candles):
    _seed_source(minutes=6, extra_timeframes=())
    source_before = _series(*SOURCE)

    result = candle_repository.copy_candles(*SOURCE, SOURCE[0], 'SPY-USDT', delete_source=True)

    assert result == {'copied': 6, 'deleted': 6}
    assert _series(*SOURCE) == []
    assert _series(SOURCE[0], 'SPY-USDT') == source_before


def test_copy_candles_refuses_self_missing_source_and_occupied_target(sqlite_candles):
    _seed_source(minutes=3, extra_timeframes=())
    Candle.insert_many([_row(*TARGET, 0, '1m')]).execute()

    with pytest.raises(ValueError, match='must differ'):
        candle_repository.copy_candles(*SOURCE, *SOURCE)
    with pytest.raises(ValueError, match='No candles are stored'):
        candle_repository.copy_candles('Binance Spot', 'BTC-USDT', *TARGET)
    with pytest.raises(candle_repository.CandlesAlreadyExist):
        candle_repository.copy_candles(*SOURCE, *TARGET)

    assert Candle.select().where(Candle.exchange == TARGET[0]).count() == 1
    assert Candle.select().where(Candle.exchange == SOURCE[0]).count() == 3


@pytest.fixture
def api_client(monkeypatch) -> TestClient:
    monkeypatch.setitem(auth.ENV_VALUES, 'PASSWORD', PASSWORD)
    app = FastAPI()

    @app.exception_handler(auth.InvalidAuthError)
    async def invalid_auth_handler(_request, _exc):
        return auth.unauthorized_response()

    app.include_router(candles_controller.router)
    return TestClient(app)


def _headers():
    return {'Authorization': AUTHORIZATION}


def test_copy_endpoint_validates_target_and_reports_the_copy(api_client, monkeypatch):
    calls = []

    def fake_copy(exchange, symbol, target_exchange, target_symbol, delete_source=False):
        calls.append((exchange, symbol, target_exchange, target_symbol, delete_source))
        if target_symbol == 'TAKEN-USDT':
            raise candle_repository.CandlesAlreadyExist('taken')
        return {'copied': 42, 'deleted': 42 if delete_source else 0}

    monkeypatch.setattr(candle_repository, 'copy_candles', fake_copy)

    base = {'exchange': 'Massive Stocks', 'symbol': 'SPY-USD'}
    ok = api_client.post('/candles/copy', json={**base, 'target_exchange': 'Binance Perpetual Futures', 'target_symbol': 'spy-usdt'}, headers=_headers())
    assert ok.status_code == 200
    assert ok.json() == {
        'message': 'Copied 42 candles from SPY-USD on Massive Stocks to SPY-USDT on Binance Perpetual Futures',
        'copied_count': 42,
        'deleted_count': 0,
        'target_exchange': 'Binance Perpetual Futures',
        'target_symbol': 'SPY-USDT',
    }
    assert calls[-1] == ('Massive Stocks', 'SPY-USD', 'Binance Perpetual Futures', 'SPY-USDT', False)

    moved = api_client.post('/candles/copy', json={**base, 'target_exchange': 'Custom Data', 'delete_source': True}, headers=_headers())
    assert moved.status_code == 200
    assert moved.json()['message'].startswith('Moved 42 candles')
    assert calls[-1] == ('Massive Stocks', 'SPY-USD', 'Custom Data', 'SPY-USD', True)

    assert api_client.post('/candles/copy', json={**base, 'target_exchange': 'Not An Exchange'}, headers=_headers()).status_code == 422
    assert api_client.post('/candles/copy', json={**base, 'target_exchange': 'Custom Data', 'target_symbol': 'SPYUSD'}, headers=_headers()).status_code == 422
    assert api_client.post('/candles/copy', json={**base, 'target_exchange': 'Custom Data', 'target_symbol': 'TAKEN-USDT'}, headers=_headers()).status_code == 409
    assert api_client.post('/candles/copy', json={**base, 'target_exchange': 'Custom Data'}).status_code == 401
    assert len(calls) == 3


def test_copy_candles_mcp_service_forwards_the_request(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(url=url, json=json)
        payload = {
            'message': 'Copied 5 candles', 'copied_count': 5, 'deleted_count': 0,
            'target_exchange': 'Binance Perpetual Futures', 'target_symbol': 'SPY-USDT',
        }
        return SimpleNamespace(status_code=200, json=lambda: payload, text='')

    monkeypatch.setattr(candles_service.mcp_config, 'JESSE_API_URL', 'http://jesse.test')
    monkeypatch.setattr(candles_service.mcp_config, 'JESSE_PASSWORD', 'pw')
    monkeypatch.setattr('requests.post', fake_post)

    result = candles_service.copy_candles_service('Massive Stocks', 'SPY-USD', 'Binance Perpetual Futures', 'SPY-USDT')

    assert captured['url'] == 'http://jesse.test/candles/copy'
    assert captured['json'] == {
        'exchange': 'Massive Stocks', 'symbol': 'SPY-USD', 'target_exchange': 'Binance Perpetual Futures',
        'target_symbol': 'SPY-USDT', 'delete_source': False,
    }
    assert result['status'] == 'success'
    assert result['action'] == 'candles_copied'
    assert result['target'] == {'exchange': 'Binance Perpetual Futures', 'symbol': 'SPY-USDT'}
    assert result['copied_count'] == 5


def test_copy_uses_time_ordered_ids_on_postgres_and_random_ids_elsewhere(sqlite_candles):
    # Random v4 keys scatter inserts across the huge primary-key index; PostgreSQL gets ordered ids.
    sqlite_sql = candle_repository._new_candle_id_sql().sql
    assert 'randomblob' in sqlite_sql

    postgres = peewee.PostgresqlDatabase('unused', autoconnect=False)
    with postgres.bind_ctx([Candle]):
        postgres_sql = candle_repository._new_candle_id_sql().sql
    assert 'clock_timestamp()' in postgres_sql
    assert postgres_sql.endswith('::uuid')
