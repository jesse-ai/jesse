"""
MCP candle management against Jesse's real candle routes.

The MCP candle services make their HTTP calls through `_Forwarder` into the real candles
routers (including the dashboard's form-authenticated CSV download), which run over a
throwaway SQLite candle table inside a disposable project directory. Only two things differ
from production, both documented at their fixtures: the PostgreSQL server-side cursor that
streams exports is replaced by an equivalent ordered SQLite query (the PostgreSQL path is
covered by the opt-in integration suite), and the process that would download candles from an
exchange is recorded instead of started. Nothing here contacts an exchange or a provider.
"""
import csv
import io
import json
import os
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import anyio
import peewee
import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

import jesse.helpers as jh
import jesse.mcp.mcp_config as mcp_config
import jesse.mcp.tools.services.candles as candles_service
from jesse.controllers import candles_controller
from jesse.mcp.server import create_mcp_server
from jesse.models.Candle import Candle
from jesse.repositories import candle_repository
from jesse.services import auth

PASSWORD = 'candle-management-password'
AUTH = sha256(PASSWORD.encode('utf-8')).hexdigest()
MINUTE = 60_000
# 2024-01-01 00:00 UTC.
T0 = 1_704_067_200_000

# Mirrors the production table: legacy rows may carry a NULL timeframe.
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


class _Forwarder:
    """Stands in for the `requests` module inside the MCP candle services and forwards to the app."""

    RequestException = requests.RequestException

    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.calls: list = []

    def post(self, url, json=None, data=None, files=None, headers=None, timeout=None):
        route = url.removeprefix('http://jesse.test')
        self.calls.append(route)
        if files is not None:
            # CSV routes must retain server tracebacks; export tests separately exercise HTTP 500 responses.
            return TestClient(self.client.app).post(route, data=data, files=files, headers=headers)
        return self.client.post(route, json=json, headers=headers)


def _row(exchange, symbol, timestamp, timeframe='1m', price=100.0):
    return {
        'id': jh.generate_unique_id(), 'exchange': exchange, 'symbol': symbol, 'timestamp': timestamp,
        'open': price, 'close': price + 0.5, 'high': price + 1.25, 'low': price - 0.75,
        'volume': 3 + timestamp / MINUTE % 7, 'timeframe': timeframe,
    }


def _seed(exchange, symbol, minutes, start=T0, timeframe='1m', step=MINUTE, price=100.0):
    rows = [_row(exchange, symbol, start + i * step, timeframe, price + i) for i in range(minutes)]
    Candle.insert_many(rows).execute()
    return rows


def _series(exchange, symbol, timeframe='1m'):
    return list(
        Candle.select(Candle.timestamp, Candle.open, Candle.close, Candle.high, Candle.low, Candle.volume)
        .where((Candle.exchange == exchange) & (Candle.symbol == symbol) & (Candle.timeframe == timeframe))
        .order_by(Candle.timestamp).tuples()
    )


def _count(exchange=None, symbol=None):
    query = Candle.select()
    if exchange is not None:
        query = query.where(Candle.exchange == exchange)
    if symbol is not None:
        query = query.where(Candle.symbol == symbol)
    return query.count()


def _sqlite_stream(exchange, symbol):
    """
    Same rows, order, and batching as candle_repository.stream_one_minute_candles, whose
    PostgreSQL named cursor SQLite cannot open.
    """
    rows = list(
        Candle.select(Candle.timestamp, Candle.open, Candle.close, Candle.high, Candle.low, Candle.volume)
        .where((Candle.exchange == exchange) & (Candle.symbol == symbol)
               & ((Candle.timeframe == '1m') | Candle.timeframe.is_null()))
        .order_by(Candle.timestamp.asc()).tuples()
    )
    size = candle_repository.CANDLE_EXPORT_BATCH_SIZE
    for start in range(0, len(rows), size):
        yield rows[start:start + size]


@pytest.fixture
def project(tmp_path, monkeypatch) -> Path:
    root = tmp_path / 'project'
    (root / 'strategies').mkdir(parents=True)
    (root / 'storage').mkdir()
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def api(tmp_path, project, monkeypatch):
    monkeypatch.setitem(auth.ENV_VALUES, 'PASSWORD', PASSWORD)
    monkeypatch.setattr(candle_repository, 'stream_one_minute_candles', _sqlite_stream)
    app = FastAPI()

    @app.exception_handler(auth.InvalidAuthError)
    async def invalid_auth_handler(_request, _exc):
        return auth.unauthorized_response()

    app.include_router(candles_controller.export_router)
    app.include_router(candles_controller.router)
    db = peewee.SqliteDatabase(str(tmp_path / 'candles.db'))
    with db.bind_ctx([Candle]):
        db.execute_sql(CANDLE_SCHEMA)
        db.execute_sql('CREATE UNIQUE INDEX candle_series ON candle (exchange, symbol, timeframe, timestamp)')
        yield TestClient(app, raise_server_exceptions=False)
    db.close()


@pytest.fixture
def forwarder(api, monkeypatch) -> _Forwarder:
    fake = _Forwarder(api)
    monkeypatch.setattr(candles_service, 'requests', fake)
    monkeypatch.setattr(mcp_config, 'JESSE_API_URL', 'http://jesse.test')
    monkeypatch.setattr(mcp_config, 'JESSE_PASSWORD', PASSWORD)
    monkeypatch.setattr(mcp_config, 'DASHBOARD_URL', None)
    return fake


def _dashboard_download(api: TestClient, exchange: str, symbol: str) -> bytes:
    """The bytes the dashboard's Export button downloads (native form POST with the token)."""
    response = api.post('/candles/export', data={'exchange': exchange, 'symbol': symbol, 'token': AUTH})
    assert response.status_code == 200
    return response.content


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def test_candle_tools_are_registered_with_bounded_schemas_and_honest_descriptions():
    tools = {tool.name: tool for tool in create_mcp_server(0)._tool_manager.list_tools()}
    expected = {
        'search_symbols', 'import_candles', 'get_candle_import_status', 'cancel_candle_import',
        'get_existing_candles', 'delete_candles', 'purge_candles', 'copy_candles', 'export_candles',
        'preview_custom_candle_csv', 'clean_and_import_custom_candle_csv', 'get_candles', 'clear_candle_cache',
    }
    assert expected <= set(tools)
    assert all(tools[name].is_async for name in expected)

    existing = tools['get_existing_candles'].parameters
    assert existing.get('required') is None
    assert existing['properties']['availability']['enum'] == ['all', 'backtesting', 'live']
    assert tools['purge_candles'].parameters['properties']['exchanges']['type'] == 'array'
    assert tools['purge_candles'].parameters['properties']['exchanges']['items'] == {'type': 'string'}
    assert tools['export_candles'].parameters['required'] == ['exchange', 'symbol']
    for name in ('preview_custom_candle_csv', 'clean_and_import_custom_candle_csv'):
        properties = tools[name].parameters['properties']
        assert {'project_path', 'file_path'} <= set(properties)
        assert 'file_path' not in tools[name].parameters['required']
        assert 'does not exist there' in tools[name].description or 'as in preview_custom_candle_csv' in tools[name].description

    # The listing documents only fields Jesse returns (no timeframe/count/from_date).
    assert 'from_date' not in tools['get_existing_candles'].description
    assert 'start_date' in tools['get_existing_candles'].description
    # get_candles is documented as the chart window with times in seconds, not the stored series.
    assert 'NOT a historical reader' in tools['get_candles'].description
    assert 'Unix seconds' in tools['get_candles'].description
    assert 'stays on the Jesse host' in tools['export_candles'].description
    # The import docs point to get_candle_import_status and list the real historical sources.
    assert 'get_candle_import_status(import_id)' in tools['import_candles'].description
    assert 'Massive Stocks' in tools['import_candles'].description
    assert 'in the same transaction' not in tools['copy_candles'].description
    # The resource agrees with the implementation: chunks commit separately and the source is
    # deleted afterwards, so copy and deletion are not one transaction.
    from importlib.resources import files
    guide = (files('jesse.mcp.resources') / 'candle.md').read_text(encoding='utf-8')
    assert 'in the same transaction' not in guide and 'not one transaction' in guide


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

def _seed_inventory():
    _seed('Binance Perpetual Futures', 'BTC-USDT', 90)
    _seed('Binance Perpetual Futures', 'BTC-USDT', 18, timeframe='5m', step=5 * MINUTE)
    _seed('Binance Perpetual Futures', 'ETH-USDT', 30, start=T0 + 2 * 86_400_000)
    _seed('Bybit Spot', 'BTC-USDT', 20)
    _seed('Hyperliquid Perpetual', 'BTC-USDC', 10)
    _seed('Custom Data', 'SPY-USD', 15, start=T0 + 86_400_000)


def test_existing_candles_lists_each_stored_pair_with_its_dates_and_dashboard_flags(forwarder):
    _seed_inventory()

    result = candles_service.get_existing_candles_service()

    assert result['status'] == 'success'
    assert (result['total_count'], result['stored_pairs_count'], result['candle_sets_count']) == (5, 5, 5)
    assert result['next_offset'] is None
    assert result['candle_sets'] == [
        {'exchange': 'Binance Perpetual Futures', 'symbol': 'BTC-USDT', 'start_date': '2024-01-01', 'end_date': '2024-01-01',
         'backtesting_supported': True, 'updatable': True},
        {'exchange': 'Binance Perpetual Futures', 'symbol': 'ETH-USDT', 'start_date': '2024-01-03', 'end_date': '2024-01-03',
         'backtesting_supported': True, 'updatable': True},
        {'exchange': 'Bybit Spot', 'symbol': 'BTC-USDT', 'start_date': '2024-01-01', 'end_date': '2024-01-01',
         'backtesting_supported': True, 'updatable': True},
        {'exchange': 'Custom Data', 'symbol': 'SPY-USD', 'start_date': '2024-01-02', 'end_date': '2024-01-02',
         'backtesting_supported': True, 'updatable': False},
        {'exchange': 'Hyperliquid Perpetual', 'symbol': 'BTC-USDC', 'start_date': '2024-01-01', 'end_date': '2024-01-01',
         'backtesting_supported': False, 'updatable': True},
    ]


def test_existing_candles_filters_match_the_manage_candles_page(forwarder):
    _seed_inventory()

    def pairs(**filters):
        result = candles_service.get_existing_candles_service(**filters)
        assert result['status'] == 'success', result
        return [(row['exchange'], row['symbol']) for row in result['candle_sets']]

    # Case-insensitive substrings, like the dashboard's exchange and symbol search inputs.
    assert pairs(exchange='binance') == [('Binance Perpetual Futures', 'BTC-USDT'), ('Binance Perpetual Futures', 'ETH-USDT')]
    assert pairs(symbol='btc') == [('Binance Perpetual Futures', 'BTC-USDT'), ('Bybit Spot', 'BTC-USDT'),
                                   ('Hyperliquid Perpetual', 'BTC-USDC')]
    assert pairs(exchange='PERP', symbol='usdc') == [('Hyperliquid Perpetual', 'BTC-USDC')]
    # "Backtesting Only" keeps backtesting exchanges; "Live Trading Only" keeps live-only ones.
    assert ('Hyperliquid Perpetual', 'BTC-USDC') not in pairs(availability='backtesting')
    assert len(pairs(availability='backtesting')) == 4
    assert pairs(availability='live') == [('Hyperliquid Perpetual', 'BTC-USDC')]
    assert pairs(exchange='nothing-like-this') == []


def test_existing_candles_pages_with_bounds_and_rejects_bad_arguments_without_a_request(forwarder):
    for index in range(7):
        _seed('Binance Spot', f'C{index}-USDT', 2)

    first = candles_service.get_existing_candles_service(limit=3)
    second = candles_service.get_existing_candles_service(offset=first['next_offset'], limit=3)
    last = candles_service.get_existing_candles_service(offset=second['next_offset'], limit=3)
    assert [first['next_offset'], second['next_offset'], last['next_offset']] == [3, 6, None]
    listed = [row['symbol'] for page in (first, second, last) for row in page['candle_sets']]
    assert listed == [f'C{index}-USDT' for index in range(7)]
    assert last['total_count'] == 7 and last['candle_sets_count'] == 1

    calls = len(forwarder.calls)
    for bad in ({'limit': 0}, {'limit': 1001}, {'offset': -1}, {'limit': True}, {'availability': 'paper'}):
        result = candles_service.get_existing_candles_service(**bad)
        assert (result['status'], result['error_type']) == ('error', 'invalid_request'), bad
    assert len(forwarder.calls) == calls


def test_existing_candles_default_page_stays_bounded_on_large_inventories(forwarder):
    Candle.insert_many([_row('Binance Spot', f'S{index:04d}-USDT', T0) for index in range(1_200)]).execute()

    default = candles_service.get_existing_candles_service()
    largest = candles_service.get_existing_candles_service(limit=1000)

    assert (default['candle_sets_count'], default['total_count'], default['next_offset']) == (200, 1_200, 200)
    assert (largest['candle_sets_count'], largest['next_offset']) == (1000, 1000)
    assert len(json.dumps(largest)) < 200_000


# ---------------------------------------------------------------------------
# Delete and purge
# ---------------------------------------------------------------------------

def test_delete_removes_every_timeframe_of_one_pair_and_reports_the_rows(forwarder):
    _seed_inventory()
    Candle.insert_many([_row('Binance Perpetual Futures', 'BTC-USDT', T0 + 999 * MINUTE, None)]).execute()

    result = candles_service.delete_candles_service('Binance Perpetual Futures', 'BTC-USDT')

    assert result['status'] == 'success' and result['deleted_count'] == 90 + 18 + 1
    assert _count('Binance Perpetual Futures', 'BTC-USDT') == 0
    assert _count('Binance Perpetual Futures', 'ETH-USDT') == 30
    assert _count('Bybit Spot', 'BTC-USDT') == 20

    again = candles_service.delete_candles_service('Binance Perpetual Futures', 'BTC-USDT')
    assert again['status'] == 'success' and again['deleted_count'] == 0
    assert 'nothing was deleted' in again['message']
    # The exchange and symbol must match exactly, as on the dashboard.
    assert candles_service.delete_candles_service('binance perpetual futures', 'ETH-USDT')['deleted_count'] == 0
    assert _count('Binance Perpetual Futures', 'ETH-USDT') == 30


def test_delete_route_keeps_its_dashboard_response_and_adds_the_count(api):
    _seed('Bybit Spot', 'BTC-USDT', 4)
    response = api.post('/candles/delete', json={'exchange': 'Bybit Spot', 'symbol': 'BTC-USDT'}, headers={'Authorization': AUTH})
    assert response.status_code == 200
    assert response.json() == {'message': 'Candles deleted successfully', 'deleted_count': 4}


def test_purge_deletes_whole_exchanges_only(forwarder):
    _seed_inventory()

    result = candles_service.purge_candles_service(['Binance Perpetual Futures', 'Bybit Spot', 'Bybit Spot'])

    assert result['status'] == 'success' and result['deleted_count'] == 90 + 18 + 30 + 20
    assert result['exchanges'] == ['Binance Perpetual Futures', 'Bybit Spot']
    assert _count('Binance Perpetual Futures') == 0 and _count('Bybit Spot') == 0
    assert _count('Hyperliquid Perpetual') == 10 and _count('Custom Data') == 15


def test_purge_rejects_ambiguous_input_without_a_request(forwarder):
    _seed_inventory()
    for bad in ([], [''], ['  '], 'Bybit Spot', [3], None, ['X'] * 101):
        result = candles_service.purge_candles_service(bad)
        assert (result['status'], result['error_type']) == ('error', 'invalid_request'), bad
    assert forwarder.calls == []
    assert _count() == 90 + 18 + 30 + 20 + 10 + 15


def test_candle_writes_need_dashboard_authentication(api, forwarder, monkeypatch):
    _seed('Bybit Spot', 'BTC-USDT', 4)
    for route, body in (('/candles/delete', {'exchange': 'Bybit Spot', 'symbol': 'BTC-USDT'}),
                        ('/candles/purge', {'exchanges': ['Bybit Spot']}),
                        ('/candles/copy', {'exchange': 'Bybit Spot', 'symbol': 'BTC-USDT', 'target_exchange': 'Binance Spot'}),
                        ('/candles/export-to-project', {'exchange': 'Bybit Spot', 'symbol': 'BTC-USDT'})):
        for headers in ({}, {'Authorization': 'wrong'}, {'Authorization': PASSWORD}):
            assert api.post(route, json=body, headers=headers).status_code == 401, route
    assert _count('Bybit Spot') == 4 and _count('Binance Spot') == 0
    assert not (Path('research_scripts')).exists()

    monkeypatch.setattr(mcp_config, 'JESSE_PASSWORD', 'not-the-password')
    for result in (candles_service.delete_candles_service('Bybit Spot', 'BTC-USDT'),
                   candles_service.purge_candles_service(['Bybit Spot']),
                   candles_service.export_candles_service('Bybit Spot', 'BTC-USDT')):
        assert result['status'] == 'error' and result['http_status'] == 401
    assert _count('Bybit Spot') == 4


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def test_export_writes_the_dashboard_download_into_research_scripts(api, forwarder, project, monkeypatch):
    monkeypatch.setattr(candle_repository, 'CANDLE_EXPORT_BATCH_SIZE', 7)
    monkeypatch.setattr(mcp_config, 'DASHBOARD_URL', 'https://dash.example')
    _seed('Binance Perpetual Futures', 'BTC-USDT', 50)
    _seed('Binance Perpetual Futures', 'BTC-USDT', 10, timeframe='5m', step=5 * MINUTE)

    result = candles_service.export_candles_service('Binance Perpetual Futures', 'BTC-USDT')

    path = 'research_scripts/candle_exports/binance-perpetual-futures_btc-usdt_1m.csv'
    assert result['status'] == 'success' and result['path'] == path
    assert result['row_count'] == 50 and result['overwritten'] is False
    assert result['columns'] == ['timestamp', 'open', 'close', 'high', 'low', 'volume']
    assert (result['first_timestamp'], result['last_timestamp']) == (T0, T0 + 49 * MINUTE)
    assert (result['first_candle_utc'], result['last_candle_utc']) == ('2024-01-01 00:00', '2024-01-01 00:49')
    assert result['dashboard_download_page'] == 'https://dash.example/#/candles/manage'
    assert "not the assistant's machine" in result['location']
    written = (project / path).read_bytes()
    # Byte-identical to what the dashboard's Export button downloads for the same pair.
    assert written == _dashboard_download(api, 'Binance Perpetual Futures', 'BTC-USDT')
    assert result['size_bytes'] == len(written)
    rows = list(csv.reader(io.StringIO(written.decode())))
    assert rows[0] == ['timestamp', 'open', 'close', 'high', 'low', 'volume']
    assert [int(row[0]) for row in rows[1:]] == [T0 + i * MINUTE for i in range(50)]
    assert [name for name in os.listdir(project / 'research_scripts' / 'candle_exports')] == [Path(path).name]


def test_export_path_rules_overwrite_and_missing_data(forwarder, project):
    _seed('Bybit Spot', 'ETH-USDT', 5)

    for bad in ('strategies/Demo/eth.csv', '/tmp/eth.csv', 'research_scripts/../eth.csv', 'research_scripts\\eth.csv',
                'research_scripts/eth.txt', 'research_scripts', '~/eth.csv', 'storage/eth.csv'):
        result = candles_service.export_candles_service('Bybit Spot', 'ETH-USDT', path=bad)
        assert (result['status'], result['error_type']) == ('error', 'invalid_path'), bad
    assert not (project / 'research_scripts').exists()

    first = candles_service.export_candles_service('Bybit Spot', 'ETH-USDT', path='research_scripts/data/eth.csv')
    assert first['status'] == 'success' and first['row_count'] == 5
    target = project / 'research_scripts' / 'data' / 'eth.csv'
    target.write_text('keep me\n')

    refused = candles_service.export_candles_service('Bybit Spot', 'ETH-USDT', path='research_scripts/data/eth.csv')
    assert (refused['error_type'], refused['http_status']) == ('already_exists', 409)
    assert target.read_text() == 'keep me\n'

    replaced = candles_service.export_candles_service('Bybit Spot', 'ETH-USDT', path='research_scripts/data/eth.csv', overwrite=True)
    assert replaced['status'] == 'success' and replaced['overwritten'] is True
    assert target.read_text().startswith('timestamp,open,close,high,low,volume\n')

    missing = candles_service.export_candles_service('Bybit Spot', 'NOPE-USDT', path='research_scripts/data/none.csv')
    assert (missing['error_type'], missing['http_status']) == ('not_found', 404)
    assert not (project / 'research_scripts' / 'data' / 'none.csv').exists()
    assert sorted(os.listdir(project / 'research_scripts' / 'data')) == ['eth.csv']


def test_an_unusable_export_target_is_refused_before_any_candle_is_read(forwarder, project, tmp_path, monkeypatch):
    """An unusable target is refused before the first candle is read, not after streaming the series."""
    _seed('Bybit Spot', 'ETH-USDT', 5)
    folder = project / 'research_scripts' / 'data'
    folder.mkdir(parents=True)
    (folder / 'eth.csv').write_text('keep me\n')
    (folder / 'folder.csv').mkdir()
    outside = tmp_path / 'outside.csv'
    outside.write_text('outside\n')
    os.symlink(outside, folder / 'link.csv')
    streamed = []

    def recording_stream(exchange, symbol):
        streamed.append((exchange, symbol))
        yield from _sqlite_stream(exchange, symbol)

    monkeypatch.setattr(candle_repository, 'stream_one_minute_candles', recording_stream)

    for path, overwrite, error_type in (('research_scripts/data/eth.csv', False, 'already_exists'),
                                        ('research_scripts/data/folder.csv', True, 'wrong_type'),
                                        ('research_scripts/data/link.csv', True, 'unsafe_path'),
                                        ('research_scripts/data/link.csv', False, 'already_exists')):
        result = candles_service.export_candles_service('Bybit Spot', 'ETH-USDT', path=path, overwrite=overwrite)
        assert (result['status'], result['error_type']) == ('error', error_type), path

    assert streamed == []
    assert (folder / 'eth.csv').read_text() == 'keep me\n' and outside.read_text() == 'outside\n'
    assert sorted(os.listdir(folder)) == ['eth.csv', 'folder.csv', 'link.csv']  # no temporary file left
    assert candles_service.export_candles_service('Bybit Spot', 'ETH-USDT', path='research_scripts/data/eth.csv',
                                                  overwrite=True)['row_count'] == 5
    assert streamed == [('Bybit Spot', 'ETH-USDT')]


def test_export_never_writes_through_a_symlinked_folder(forwarder, project, tmp_path):
    _seed('Bybit Spot', 'ETH-USDT', 5)
    outside = tmp_path / 'outside'
    outside.mkdir()
    (project / 'research_scripts').mkdir()
    os.symlink(outside, project / 'research_scripts' / 'candle_exports', target_is_directory=True)

    result = candles_service.export_candles_service('Bybit Spot', 'ETH-USDT')

    assert (result['status'], result['error_type']) == ('error', 'unsafe_path')
    assert os.listdir(outside) == []


def test_an_export_that_fails_midway_publishes_nothing(forwarder, project, monkeypatch):
    _seed('Bybit Spot', 'ETH-USDT', 10)
    monkeypatch.setattr(candle_repository, 'CANDLE_EXPORT_BATCH_SIZE', 3)

    def failing_stream(exchange, symbol):
        stream = _sqlite_stream(exchange, symbol)
        yield next(stream)
        raise peewee.OperationalError('connection lost')

    monkeypatch.setattr(candle_repository, 'stream_one_minute_candles', failing_stream)

    result = candles_service.export_candles_service('Bybit Spot', 'ETH-USDT')

    assert result['status'] == 'error' and result['http_status'] == 500
    folder = project / 'research_scripts' / 'candle_exports'
    assert os.listdir(folder) == []  # Neither the CSV nor the temporary file is left behind.


def test_export_reports_the_rows_it_wrote_even_when_candles_change_meanwhile(forwarder, project, monkeypatch):
    """The reported row count and bounds are those of the rows written to the file."""
    _seed('Bybit Spot', 'ETH-USDT', 12)
    # Bounds that no longer match what is stored when the rows are streamed (a concurrent import).
    monkeypatch.setattr(candle_repository, 'get_candle_timestamp_bounds', lambda *_args: (T0 - 60 * MINUTE, T0 + 999 * MINUTE))
    result = candles_service.export_candles_service('Bybit Spot', 'ETH-USDT', path='research_scripts/data/eth.csv')
    rows = list(csv.reader(io.StringIO((project / 'research_scripts' / 'data' / 'eth.csv').read_text())))[1:]
    assert (result['row_count'], result['first_timestamp'], result['last_timestamp']) == (
        len(rows), int(rows[0][0]), int(rows[-1][0])) == (12, T0, T0 + 11 * MINUTE)

    # Deleted between the check and the stream: nothing is published, not a header-only file.
    monkeypatch.setattr(candle_repository, 'stream_one_minute_candles', lambda *_args: iter(()))
    missing = candles_service.export_candles_service('Bybit Spot', 'ETH-USDT', path='research_scripts/data/gone.csv')
    assert (missing['error_type'], missing['http_status']) == ('not_found', 404)
    assert sorted(os.listdir(project / 'research_scripts' / 'data')) == ['eth.csv']


# ---------------------------------------------------------------------------
# Custom Data import from project files, round trip, and duplicate handling
# ---------------------------------------------------------------------------

def _write_csv(project: Path, relative: str, rows) -> str:
    path = project / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['timestamp', 'open', 'close', 'high', 'low', 'volume'])
        writer.writerows(rows)
    return relative


def test_export_then_import_as_custom_data_round_trips_every_value(api, forwarder, project):
    source = _seed('Binance Perpetual Futures', 'SOL-USDT', 40, price=21.125)

    exported = candles_service.export_candles_service('Binance Perpetual Futures', 'SOL-USDT')
    preview = candles_service.preview_custom_candle_csv_service(project_path=exported['path'], symbol='sol-usdt')
    imported = candles_service.clean_and_import_custom_candle_csv_service(
        project_path=exported['path'], symbol='sol-usdt', invalid_row_policy='reject')

    assert preview['status'] == 'success' and preview['project_path'] == exported['path'], preview
    assert preview['cleaning_report']['cleaned_row_count'] == 40 and preview['import_preview']['valid'] is True
    assert imported['status'] == 'success'
    assert (imported['exchange'], imported['symbol'], imported['project_path']) == ('Custom Data', 'SOL-USDT', exported['path'])
    assert _series('Custom Data', 'SOL-USDT') == _series('Binance Perpetual Futures', 'SOL-USDT')
    assert len(_series('Custom Data', 'SOL-USDT')) == len(source)

    again = candles_service.export_candles_service('Custom Data', 'SOL-USDT')
    original_lines = (project / exported['path']).read_text().splitlines()
    assert (project / again['path']).read_text().splitlines() == original_lines


def test_custom_import_keeps_stored_timestamps_and_adds_new_ones(forwarder, project):
    first = _write_csv(project, 'research_scripts/in/a.csv', [(T0 + i * MINUTE, 10, 11, 12, 9, 1) for i in range(10)])
    second = _write_csv(project, 'research_scripts/in/b.csv', [(T0 + i * MINUTE, 50, 51, 52, 49, 5) for i in range(5, 15)])

    assert candles_service.clean_and_import_custom_candle_csv_service(
        project_path=first, symbol='ABC-USD', invalid_row_policy='reject')['status'] == 'success'
    result = candles_service.clean_and_import_custom_candle_csv_service(
        project_path=second, symbol='ABC-USD', invalid_row_policy='reject')

    assert result['status'] == 'success' and 'keep their existing values' in result['message']
    stored = _series('Custom Data', 'ABC-USD')
    assert [row[0] for row in stored] == [T0 + i * MINUTE for i in range(15)]
    assert [row[1] for row in stored] == [10.0] * 10 + [50.0] * 5


def test_custom_import_reports_file_duplicates_and_refuses_conflicts(forwarder, project):
    identical = _write_csv(project, 'research_scripts/in/dup.csv',
                           [(T0 + MINUTE, 10, 11, 12, 9, 1), (T0, 10, 11, 12, 9, 1), (T0 + MINUTE, 10, 11, 12, 9, 1)])
    conflicting = _write_csv(project, 'research_scripts/in/conflict.csv',
                             [(T0, 10, 11, 12, 9, 1), (T0, 20, 21, 22, 19, 2)])

    preview = candles_service.preview_custom_candle_csv_service(project_path=identical, symbol='DUP-USD')
    assert preview['cleaning_report']['duplicate_count'] == 1 and preview['cleaning_report']['ordering_failure_count'] == 1
    assert candles_service.clean_and_import_custom_candle_csv_service(
        project_path=identical, symbol='DUP-USD', invalid_row_policy='reject')['status'] == 'success'
    assert [row[0] for row in _series('Custom Data', 'DUP-USD')] == [T0, T0 + MINUTE]

    refused = candles_service.clean_and_import_custom_candle_csv_service(
        project_path=conflicting, symbol='CON-USD', invalid_row_policy='drop')
    assert (refused['status'], refused['error_type']) == ('error', 'validation_error')
    assert refused['cleaning_report']['conflicting_duplicate_count'] == 1
    assert _count('Custom Data', 'CON-USD') == 0


def test_custom_csv_sources_are_confined_and_explicit(forwarder, project, tmp_path):
    good = _write_csv(project, 'research_scripts/in/ok.csv', [(T0, 10, 11, 12, 9, 1)])
    outside = tmp_path / 'outside.csv'
    outside.write_text('timestamp,open,close,high,low,volume\n')
    os.symlink(outside, project / 'research_scripts' / 'in' / 'link.csv')
    (project / 'research_scripts' / 'in' / 'notes.txt').write_text('x')

    def error(**kwargs):
        result = candles_service.preview_custom_candle_csv_service(symbol='OK-USD', **kwargs)
        assert result['status'] == 'error', kwargs
        return result['error_type']

    assert error() == 'validation_error'
    assert error(project_path=good, file_path=str(project / good)) == 'validation_error'
    for bad in ('/etc/passwd.csv', '../x.csv', 'storage/x.csv', 'research_scripts/../strategies/x.csv'):
        assert error(project_path=bad) == 'invalid_path', bad
    assert error(project_path='research_scripts/in/missing.csv') == 'not_found'
    assert error(project_path='research_scripts/in/link.csv') == 'unsafe_path'
    assert error(project_path='research_scripts/in/notes.txt') == 'validation_error'
    assert error(file_path='research_scripts/in/ok.csv') == 'validation_error'  # file_path must be absolute
    assert forwarder.calls == []

    # An absolute path on the Jesse host still works for an assistant on the same machine.
    local = candles_service.preview_custom_candle_csv_service(file_path=str(project / good), symbol='OK-USD')
    assert local['status'] == 'success' and local['file_path'] == str((project / good).resolve()), local


def test_custom_csv_network_errors_are_not_reported_as_validation_errors(project, monkeypatch):
    # requests' exceptions are OSError subclasses; they must be reported as connection errors.
    good = _write_csv(project, 'research_scripts/in/ok.csv', [(T0, 10, 11, 12, 9, 1)])

    def refuse(*_args, **_kwargs):
        raise requests.ConnectionError('refused')

    monkeypatch.setattr(candles_service, 'requests', SimpleNamespace(post=refuse, RequestException=requests.RequestException))
    monkeypatch.setattr(mcp_config, 'JESSE_API_URL', 'http://jesse.test')
    monkeypatch.setattr(mcp_config, 'JESSE_PASSWORD', PASSWORD)
    for service in (candles_service.preview_custom_candle_csv_service, candles_service.clean_and_import_custom_candle_csv_service):
        # Absolute host paths work on Windows too; this test isolates HTTP failure handling.
        kwargs = {'file_path': str(project / good), 'symbol': 'OK-USD'}
        if service is candles_service.clean_and_import_custom_candle_csv_service:
            kwargs['invalid_row_policy'] = 'reject'
        assert service(**kwargs)['error_type'] == 'network_error'


# ---------------------------------------------------------------------------
# Copy (dashboard parity through the real route)
# ---------------------------------------------------------------------------

def test_copy_through_mcp_matches_the_dashboard_rules(forwarder):
    _seed('Massive Stocks', 'SPY-USD', 12)
    _seed('Massive Stocks', 'SPY-USD', 3, timeframe='5m', step=5 * MINUTE)
    _seed('Binance Perpetual Futures', 'TAKEN-USDT', 1)

    copied = candles_service.copy_candles_service('Massive Stocks', 'SPY-USD', 'Binance Perpetual Futures', 'spy-usdt')
    assert copied['status'] == 'success' and copied['action'] == 'candles_copied'
    assert (copied['copied_count'], copied['deleted_count']) == (15, 0)
    assert copied['target'] == {'exchange': 'Binance Perpetual Futures', 'symbol': 'SPY-USDT'}
    assert _series('Binance Perpetual Futures', 'SPY-USDT') == _series('Massive Stocks', 'SPY-USD')
    assert _count('Massive Stocks', 'SPY-USD') == 15

    def refused(target_exchange, target_symbol=None, source=('Massive Stocks', 'SPY-USD')):
        result = candles_service.copy_candles_service(*source, target_exchange, target_symbol)
        assert result['status'] == 'error'
        return result['http_status']

    assert refused('Binance Perpetual Futures', 'TAKEN-USDT') == 409  # never merged
    assert refused('Binance Perpetual Futures', 'SPY-USDT') == 409
    assert refused('Hyperliquid Perpetual', 'SPY-USDC') == 422  # not backtesting-capable
    assert refused('Binance Perpetual Futures', 'SPYUSDT') == 422  # not BASE-QUOTE
    assert refused('Massive Stocks') == 422  # onto itself
    assert refused('Binance Spot', 'X-USDT', source=('Massive Stocks', 'NONE-USD')) == 422  # nothing stored
    assert _count('Binance Perpetual Futures', 'TAKEN-USDT') == 1

    # Same exchange, new symbol, deleting the original: the dashboard's "Move".
    moved = candles_service.copy_candles_service('Binance Perpetual Futures', 'SPY-USDT', 'Binance Perpetual Futures',
                                                 'SPYX-USDT', delete_source=True)
    assert moved['action'] == 'candles_moved' and (moved['copied_count'], moved['deleted_count']) == (15, 15)
    assert _count('Binance Perpetual Futures', 'SPY-USDT') == 0
    assert _series('Binance Perpetual Futures', 'SPYX-USDT') == _series('Massive Stocks', 'SPY-USD')


# ---------------------------------------------------------------------------
# Import start, chart window
# ---------------------------------------------------------------------------

def test_import_uses_jesse_validation_and_the_background_process(forwarder, monkeypatch):
    from jesse.modes import import_candles_mode
    from jesse.services.multiprocessing import process_manager

    outcomes, tasks = [], []
    monkeypatch.setattr(import_candles_mode, 'store_import_outcome', lambda *args: outcomes.append(args))
    monkeypatch.setattr(process_manager, 'add_task', lambda function, *args: tasks.append((function.__name__, args)))

    unsupported = candles_service.import_candles_service('Custom Data', 'SPY-USD', '2024-01-01', import_id='imp-1')
    future = candles_service.import_candles_service('Binance Spot', 'BTC-USDT', '2999-01-01', import_id='imp-2')
    malformed = candles_service.import_candles_service('Binance Spot', 'BTCUSDT', '2024-01-01', import_id='imp-3')
    started = candles_service.import_candles_service('Binance Spot', 'BTC-USDT', '2024-01-01', import_id='imp-4')

    for result in (unsupported, future, malformed):
        assert (result['status'], result['http_status']) == ('error', 422)
    assert 'not a supported historical provider' in unsupported['message']
    assert "Future's date is not accepted" in future['message']
    assert started['status'] == 'started' and started['import_id'] == 'imp-4'
    assert [outcome[:2] for outcome in outcomes] == [('imp-1', 'failed'), ('imp-2', 'failed'), ('imp-3', 'failed'), ('imp-4', 'running')]
    # The download process is handed to the process manager, which is recorded here instead.
    assert tasks == [('run', ('imp-4', 'Binance Spot', 'BTC-USDT', '2024-01-01'))]


def test_get_candles_returns_a_bounded_newest_window(monkeypatch):
    requests_made = []

    def fake_post(url, json=None, headers=None, timeout=None):
        requests_made.append(json)
        payload = {'id': json['id'], 'data': [{'time': 1_700_000_000 + 60 * i, 'open': i, 'close': i, 'high': i, 'low': i,
                                               'volume': 1} for i in range(1_500)]}
        return SimpleNamespace(status_code=200, json=lambda: payload, text='')

    monkeypatch.setattr(candles_service, 'requests', SimpleNamespace(post=fake_post, RequestException=requests.RequestException))
    monkeypatch.setattr(mcp_config, 'JESSE_API_URL', 'http://jesse.test')
    monkeypatch.setattr(mcp_config, 'JESSE_PASSWORD', PASSWORD)

    default = candles_service.get_candles_service('Binance Spot', 'BTC-USDT', '1m')
    largest = candles_service.get_candles_service('Binance Spot', 'BTC-USDT', '1m', limit=1000)

    assert (default['candle_count'], default['total_in_window'], default['truncated']) == (300, 1_500, True)
    assert default['candles'][0]['open'] == 1_200 and default['candles'][-1]['open'] == 1_499
    assert largest['candle_count'] == 1000 and 'Unix seconds' in default['window']
    for bad in ({'limit': 0}, {'limit': 1001}, {'limit': True}, {'timeframe': '7m'}):
        kwargs = {'exchange': 'Binance Spot', 'symbol': 'BTC-USDT', 'timeframe': '1m', **bad}
        assert candles_service.get_candles_service(**kwargs)['error_type'] == 'invalid_request', bad
    assert len(requests_made) == 2


def test_candle_tools_run_through_fastmcp_with_argument_validation(forwarder):
    """The registered async tools reach the same services, and FastMCP validates types first."""
    _seed_inventory()
    mcp = create_mcp_server(0)

    async def call(name, arguments):
        content = await mcp.call_tool(name, arguments)
        return json.loads(content[0][0].text) if isinstance(content, tuple) else json.loads(content[0].text)

    async def scenario():
        listed = await call('get_existing_candles', {'availability': 'live'})
        purge = await call('purge_candles', {'exchanges': ['Hyperliquid Perpetual']})
        with pytest.raises(Exception):
            await mcp.call_tool('purge_candles', {'exchanges': 'Hyperliquid Perpetual'})
        return listed, purge

    listed, purge = anyio.run(scenario)
    assert [row['symbol'] for row in listed['candle_sets']] == ['BTC-USDC']
    assert purge['deleted_count'] == 10 and _count('Hyperliquid Perpetual') == 0
