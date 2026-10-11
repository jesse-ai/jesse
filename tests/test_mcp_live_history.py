"""
Live/paper trade and order history by date window: get_live_trades, get_live_orders, and
{"dataset": ...} inputs of run_analysis, against Jesse's real models, queries, routes, and tools.

Every test binds the real ClosedTrade, Order, LiveSession, and saved-key models to a throwaway
SQLite file and seeds rows through the models. The real session-results and analysis routers
serve them (FastAPI TestClient), the MCP tools reach them through their normal HTTP services,
and analysis jobs run real Python/matplotlib in a disposable project. Three boundaries are
replaced: the live-plugin check (a switch), the clock of live_history (frozen), and the Redis
set of running session workers (a Python set). Nothing starts a session, contacts an exchange,
or reads a real env, key, or wallet file; key values are fake sentinels checked for in every
response. PostgreSQL itself is covered by the opt-in disposable-instance test
(test_mcp_session_analysis_integration.py).
"""
import asyncio
import base64
import json
import math
import os
import random
import sqlite3
import threading
import time
import types
import uuid
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

import peewee
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mcp.types import CallToolResult, ImageContent, TextContent

import jesse.mcp.tools.services.project_files as project_files_service
import jesse.helpers as jh
from jesse.controllers import analysis_controller, closed_trade_controller, session_results_controller
from jesse.mcp import server as mcp_server
from jesse.mcp.agent_rules import _load_packaged_rules
from jesse.mcp.resources import register_resources
from jesse.mcp.tools import register_tools
from jesse.models.ClosedTrade import ClosedTrade
from jesse.models.ExchangeApiKeys import ExchangeApiKeys
from jesse.models.LiveEquitySnapshot import LiveEquitySnapshot
from jesse.models.LiveSession import LiveSession
from jesse.models.Log import Log
from jesse.models.NotificationApiKeys import NotificationApiKeys
from jesse.models.Order import Order
from jesse.repositories import closed_trade_repository, live_session_repository, order_repository
from jesse.repositories.closed_trade_repository import populate_order_arrays
from jesse.services import analysis_jobs, auth, live_history, research_jobs, session_results
from jesse.services.multiprocessing import process_manager
from jesse.services.project_files import ProjectFileError
from jesse.services.transformers import get_closed_trade_details
from tests.mcp_tool_adapters import callable_tool

PASSWORD = 'live-history-password'
HEADERS = {'Authorization': sha256(PASSWORD.encode('utf-8')).hexdigest()}
WAIT_SECONDS = 60
MODELS = [ClosedTrade, Order, LiveSession, ExchangeApiKeys, NotificationApiKeys, LiveEquitySnapshot, Log]

DAY = 24 * 60 * 60 * 1000
# 2026-09-28T12:00:00Z, the frozen "now" of every test.
NOW = int(datetime(2026, 9, 28, 12, tzinfo=timezone.utc).timestamp() * 1000)
START = '2026-09-21T00:00:00Z'
START_MS = int(datetime(2026, 9, 21, tzinfo=timezone.utc).timestamp() * 1000)
END = '2026-09-22T00:00:00Z'
END_MS = START_MS + DAY

BYBIT = 'Bybit USDT Perpetual'
BINANCE = 'Binance Perpetual Futures'
KEY_A, KEY_B, TELEGRAM = (str(uuid.uuid4()) for _ in range(3))
# Fake credential values; none of them may ever appear in a response or a snapshot.
FAKE_KEY_A = 'FAKE-KEY-A-0123456789'
FAKE_SECRET_A = 'FAKE-SECRET-A-9876543210'
FAKE_PASSPHRASE_A = 'FAKE-PASSPHRASE-A-555'
FAKE_KEY_B = 'FAKE-KEY-B-0123456789'
FAKE_SECRET_B = 'FAKE-SECRET-B-9876543210'
FAKE_BOT_TOKEN = 'FAKE-BOT-TOKEN-424242'
ALL_FAKES = (FAKE_KEY_A, FAKE_SECRET_A, FAKE_PASSPHRASE_A, FAKE_KEY_B, FAKE_SECRET_B, FAKE_BOT_TOKEN)


class FakeMCP:
    def __init__(self):
        self.tools = {}
        self.resources = {}

    def tool(self):
        def decorator(func):
            self.tools[func.__name__] = callable_tool(func)
            return func
        return decorator

    def resource(self, uri):
        def decorator(func):
            self.resources[uri] = func
            return func
        return decorator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def project(tmp_path, monkeypatch) -> Path:
    root = tmp_path / 'project'
    (root / 'storage').mkdir(parents=True)
    monkeypatch.chdir(root)
    monkeypatch.setattr(research_jobs, 'TERMINATE_GRACE_SECONDS', 1.0)
    monkeypatch.setattr(research_jobs, '_POLL_SECONDS', 0.05)
    yield root
    research_jobs.terminate_all_jobs()
    with research_jobs._jobs_lock:
        research_jobs._jobs.clear()
    analysis_jobs._preparing.clear()


@pytest.fixture
def db(tmp_path):
    """The real models on a throwaway SQLite file (one connection per thread, as TestClient uses threads)."""
    database = peewee.SqliteDatabase(str(tmp_path / 'history.db'), pragmas={'busy_timeout': 5000})
    with database.bind_ctx(MODELS):
        database.create_tables(MODELS)
        created = datetime(2026, 9, 1)
        ExchangeApiKeys.create(id=KEY_A, exchange_name=BYBIT, name='bybit main', api_key=FAKE_KEY_A,
                               api_secret=FAKE_SECRET_A, additional_fields=json.dumps({'api_passphrase': FAKE_PASSPHRASE_A}),
                               created_at=created)
        ExchangeApiKeys.create(id=KEY_B, exchange_name=BINANCE, name='binance main', api_key=FAKE_KEY_B,
                               api_secret=FAKE_SECRET_B, additional_fields='{}', created_at=created)
        NotificationApiKeys.create(id=TELEGRAM, name='phone', driver='telegram',
                                   fields=json.dumps({'bot_token': FAKE_BOT_TOKEN, 'chat_id': '12'}), created_at=created)
        yield database
    database.close()


@pytest.fixture
def plugin(monkeypatch) -> dict:
    state = {'installed': True}
    monkeypatch.setattr(session_results, '_live_plugin_available', lambda: state['installed'])
    return state


@pytest.fixture
def clock(monkeypatch) -> dict:
    state = {'now': NOW}
    monkeypatch.setattr(live_history, '_now_ms', lambda: state['now'])
    return state


@pytest.fixture
def workers(monkeypatch) -> set:
    """Session IDs with a running worker (the Redis set in production)."""
    active: set = set()
    monkeypatch.setattr(type(process_manager), 'active_workers', property(lambda _self: set(active)))
    return active


class _RepositoryHelpers(types.SimpleNamespace):
    """jesse.helpers for the dashboard's repositories, without the unit-test guard that skips the database."""

    def __getattr__(self, name):
        return getattr(jh, name)

    @staticmethod
    def is_unit_testing() -> bool:
        return False


@pytest.fixture
def api(project, db, plugin, clock, workers, monkeypatch) -> TestClient:
    monkeypatch.setitem(auth.ENV_VALUES, 'PASSWORD', PASSWORD)
    # The dashboard's own closed-trade routes serve as the reference for trade values.
    monkeypatch.setattr(closed_trade_repository, 'jh', _RepositoryHelpers())
    monkeypatch.setattr(order_repository, 'jh', _RepositoryHelpers())
    # Per-session reads (get_session_results, live session snapshots) load the row through it.
    monkeypatch.setattr(live_session_repository, 'jh', _RepositoryHelpers())
    app = FastAPI()

    @app.exception_handler(auth.InvalidAuthError)
    async def invalid_auth_handler(_request, _exc):
        return auth.unauthorized_response()

    app.include_router(session_results_controller.router)
    app.include_router(analysis_controller.router)
    app.include_router(closed_trade_controller.router)
    from jesse.controllers import order_controller
    app.include_router(order_controller.router)
    return TestClient(app)


@pytest.fixture
def tools(api, monkeypatch) -> dict:
    """The registered MCP tools, whose HTTP services reach the test API."""
    def forward_post(url, json=None, headers=None, timeout=None):
        return api.post(url.removeprefix('http://jesse.test'), json=json, headers=headers)

    monkeypatch.setattr(project_files_service.mcp_config, 'JESSE_API_URL', 'http://jesse.test')
    monkeypatch.setattr(project_files_service.mcp_config, 'JESSE_PASSWORD', PASSWORD)
    monkeypatch.setattr(project_files_service.requests, 'post', forward_post)
    mcp = FakeMCP()
    register_tools(mcp)
    return mcp.tools


# ---------------------------------------------------------------------------
# Seeding through the real models
# ---------------------------------------------------------------------------

def _session(mode: str = 'livetrade', status: str = 'stopped', key: str = None, notification: str = None,
             title: str = 'session', exchange: str = BYBIT, state: str = None) -> str:
    session_id = str(uuid.uuid4())
    form = {'exchange': exchange, 'exchange_api_key_id': key or '', 'notification_api_key_id': notification or '',
            'routes': [{'strategy': 'Demo', 'symbol': 'BTC-USDT', 'timeframe': '1h'}]}
    LiveSession.create(id=session_id, status=status, session_mode=mode, exchange=exchange, title=title,
                       state=json.dumps({'form': form}) if state is None else state,
                       created_at=START_MS - DAY, updated_at=START_MS - DAY, finished_at=None)
    return session_id


def _order(session_id: str, created_at: int, *, trade_id: str = None, side: str = 'buy', qty: float = 1.0,
           price: float = 100.0, status: str = 'EXECUTED', executed_at: int = None, canceled_at: int = None,
           fee: float = None, mode: str = 'livetrade', exchange: str = BYBIT, symbol: str = 'BTC-USDT',
           exchange_id: str = None, jesse_submitted: bool = True, order_id: str = None) -> str:
    order_id = order_id or str(uuid.uuid4())
    Order.create(id=order_id, trade_id=trade_id, session_id=session_id, exchange_id=exchange_id, symbol=symbol,
                 exchange=exchange, side=side, type='MARKET', reduce_only=False, qty=qty,
                 filled_qty=qty if status == 'EXECUTED' else 0, price=price, status=status, created_at=created_at,
                 updated_at=created_at, executed_at=executed_at, canceled_at=canceled_at, session_mode=mode, fee=fee,
                 jesse_submitted=jesse_submitted)
    return order_id


def _trade(session_id: str, closed_at, *, mode: str = 'livetrade', exchange: str = BYBIT, symbol: str = 'BTC-USDT',
           kind: str = 'long', entry: float = 100.0, exit: float = 110.0, qty: float = 2.0, fees=(0.1, 0.2),
           opened_at: int = None, soft_deleted: bool = False, leverage: int = 1, trade_id: str = None) -> str:
    """A trade with an executed entry and exit order (exit only when closed)."""
    trade_id = trade_id or str(uuid.uuid4())
    opened_at = opened_at if opened_at is not None else (closed_at or START_MS) - 3_600_000
    ClosedTrade.create(id=trade_id, session_id=session_id, strategy_name='Demo', symbol=symbol, exchange=exchange,
                       type=kind, timeframe='1h', opened_at=opened_at, closed_at=closed_at, leverage=leverage,
                       created_at=opened_at, updated_at=closed_at or opened_at, session_mode=mode,
                       soft_deleted_at=NOW if soft_deleted else None)
    entry_side, exit_side = ('buy', 'sell') if kind == 'long' else ('sell', 'buy')
    _order(session_id, opened_at, trade_id=trade_id, side=entry_side, qty=qty if kind == 'long' else -qty, price=entry,
           executed_at=opened_at, fee=fees[0], mode=mode, exchange=exchange, symbol=symbol)
    if closed_at is not None:
        _order(session_id, closed_at, trade_id=trade_id, side=exit_side, qty=-qty if kind == 'long' else qty, price=exit,
               executed_at=closed_at, fee=fees[1], mode=mode, exchange=exchange, symbol=symbol)
    return trade_id


def _post(api: TestClient, route: str, payload: dict, expect: int = 200) -> dict:
    response = api.post(f'/session-results/{route}', json=payload, headers=HEADERS)
    assert response.status_code == expect, response.text
    return response.json()


def _trades(api, expect: int = 200, **payload) -> dict:
    return _post(api, 'live-trades', payload, expect)


def _orders(api, expect: int = 200, **payload) -> dict:
    return _post(api, 'live-orders', payload, expect)


def _ids(page: dict) -> list:
    return [item['id'] for item in page['items']]


def test_shared_history_preserves_dashboard_filters_and_mcp_timestamp_semantics(api, monkeypatch):
    """Dashboard searches remain substring/opened-at; analytics use exact/closed-at selection."""
    monkeypatch.setattr(jh, 'now_to_timestamp', lambda: END_MS)
    session = _session()
    old_open = _trade(session, START_MS + 1000, opened_at=START_MS - 10 * DAY)
    current = _trade(session, START_MS + 2000, opened_at=START_MS + 1000)
    paper = _trade(session, START_MS + 3000, opened_at=START_MS + 2000, mode='papertrade')
    deleted = _trade(session, START_MS + 4000, opened_at=START_MS + 3000, soft_deleted=True)
    open_id = _trade(session, None, opened_at=START_MS + 4000)
    response = api.post('/closed-trades/live-history', headers=HEADERS,
                        json={'symbol_filter': 'BTC', 'exchange_filter': 'Bybit', 'date_filter': '7_days'})
    assert response.status_code == 200
    ids = [row['id'] for row in response.json()['trades']]
    assert old_open not in ids and set(ids) == {current, paper, deleted, open_id}
    assert ids[0] == open_id
    page = api.post('/closed-trades/live-history', headers=HEADERS,
                    json={'symbol_filter': 'BTC', 'date_filter': '7_days', 'offset': 1, 'limit': 2}).json()
    assert [row['id'] for row in page['trades']] == ids[1:3]
    assert set(_ids(_trades(api, start=START, end=END))) == {old_open, current}
    assert _ids(_trades(api, start=START, end=END, symbol='BTC')) == []


def test_order_dashboard_and_mcp_share_selection_without_changing_search_contract(api, monkeypatch):
    """Equivalent explicit scopes agree; dashboard side/type/id searches keep working."""
    monkeypatch.setattr(jh, 'now_to_timestamp', lambda: END_MS)
    session = _session()
    first = _order(session, START_MS, executed_at=START_MS + 500, exchange_id='venue-needle')
    second = _order(session, START_MS + 1000, executed_at=START_MS + 1500)
    _order(session, START_MS + 2000, side='sell', status='CANCELED')
    body = {'date_filter': '7_days', 'symbol_filter': 'BTC', 'exchange_filter': 'Bybit',
            'status_filter': 'EXECUTED', 'side_filter': 'buy', 'type_filter': 'MARK'}
    dashboard = api.post('/orders/live-history', headers=HEADERS, json=body)
    assert dashboard.status_code == 200
    assert [row['id'] for row in dashboard.json()['orders']] == [second, first]
    assert _ids(_orders(api, start=START, end=END, status='EXECUTED')) == [second, first]
    body.update(id_search='needle')
    result = api.post('/orders/live-history', headers=HEADERS, json=body).json()
    assert [row['id'] for row in result['orders']] == [first]


def test_shared_queries_and_hydration_leave_caller_transaction_intact(api, db):
    """Repository builders neither execute/rollback nor change ownership of the snapshot."""
    session = _session()
    with db.atomic():
        trade_id = _trade(session, START_MS)
        depth = db.transaction_depth()
        selection = closed_trade_repository.history_query(session_id=session, time_field='closed_at',
                                                           start_ms=START_MS, end_ms=END_MS)
        trade = selection.get()
        orders = list(order_repository.executed_for_trades_query([trade_id]).order_by(Order.executed_at, Order.id))
        closed_trade_repository.attach_executed_orders(trade, orders)
        expected = (trade.qty, trade.entry_price, trade.exit_price, trade.pnl)
        closed_trade_repository.attach_executed_orders(trade, orders)
        assert (trade.qty, trade.entry_price, trade.exit_price, trade.pnl) == expected
        assert len(trade.buy_orders) == 1 and len(trade.sell_orders) == 1
        assert order_repository.history_query(session_id=session).count() == 2
        assert db.transaction_depth() == depth
        db.rollback()
    assert ClosedTrade.select().where(ClosedTrade.id == trade_id).count() == 0


def _no_fakes(value) -> None:
    text = json.dumps(value) if not isinstance(value, str) else value
    for fake in ALL_FAKES:
        assert fake not in text


# ---------------------------------------------------------------------------
# Authentication and the plugin gate
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('route', ['live-trades', 'live-orders'])
def test_routes_require_dashboard_authentication(api, route):
    assert api.post(f'/session-results/{route}', json={}).status_code == 401
    assert api.post(f'/session-results/{route}', json={}, headers={'Authorization': 'wrong'}).status_code == 401
    # The raw password is not the credential; only its hash is.
    assert api.post(f'/session-results/{route}', json={}, headers={'Authorization': PASSWORD}).status_code == 401


def test_without_the_live_plugin_nothing_is_read(api, tools, plugin, project):
    session = _session()
    _trade(session, START_MS + 10)
    plugin['installed'] = False
    for route in ('live-trades', 'live-orders'):
        assert _post(api, route, {}, 403)['error_type'] == 'live_plugin_unavailable'
    assert tools['get_live_trades'](recent_days=3)['error_type'] == 'live_plugin_unavailable'
    assert tools['get_live_orders']()['error_type'] == 'live_plugin_unavailable'
    refused = api.post('/analysis/run', headers=HEADERS,
                       json={'code': 'print(1)', 'inputs': [{'dataset': 'live_trades', 'recent_days': 7}]})
    assert refused.status_code == 403 and refused.json()['error_type'] == 'live_plugin_unavailable'
    assert not (project / 'storage' / 'mcp' / 'analysis').exists()


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

def test_the_window_includes_its_start_and_excludes_its_end(api):
    session = _session()
    edges = {name: _trade(session, at) for name, at in
             (('before', START_MS - 1), ('start', START_MS), ('last', END_MS - 1), ('end', END_MS))}
    page = _trades(api, start=START, end=END, order='oldest_first')
    assert _ids(page) == [edges['start'], edges['last']]
    assert page['range'] == {'start': '2026-09-21T00:00:00.000Z', 'end': '2026-09-22T00:00:00.000Z',
                             'start_ms': START_MS, 'end_ms': END_MS, 'bounds': 'start inclusive, end exclusive (UTC)',
                             'source': 'start_end', 'recent_days': None}

    for at in (START_MS - 1, START_MS, END_MS - 1, END_MS):
        _order(session, at, status='ACTIVE')
    orders = _orders(api, start=START, end=END, status='ACTIVE', order='oldest_first')
    assert [item['created_at'] for item in orders['items']] == [START_MS, END_MS - 1]


@pytest.mark.parametrize('start, end', [
    ('2026-09-21T03:00:00+03:00', '2026-09-22T03:00:00+03:00'),
    ('2026-09-20T19:30:00-04:30', '2026-09-21T19:30:00-04:30'),
    ('2026-09-21T00:00:00.000z', '2026-09-22T00:00:00Z'),
    ('2026-09-21t00:00:00+00:00', '2026-09-22T00:00:00-00:00'),
])
def test_offsets_are_converted_to_utc(api, start, end):
    session = _session()
    inside = _trade(session, START_MS)
    _trade(session, END_MS)
    page = _trades(api, start=start, end=end)
    assert (page['range']['start_ms'], page['range']['end_ms']) == (START_MS, END_MS)
    assert page['range']['start'] == '2026-09-21T00:00:00.000Z'
    assert _ids(page) == [inside]


def test_milliseconds_are_honoured_exactly(api):
    session = _session()
    trades = [_trade(session, START_MS + ms) for ms in (499, 500, 749, 750)]
    page = _trades(api, start='2026-09-21T00:00:00.5Z', end='2026-09-21T00:00:00.75Z', order='oldest_first')
    assert (page['range']['start_ms'], page['range']['end_ms']) == (START_MS + 500, START_MS + 750)
    assert _ids(page) == [trades[1], trades[2]]


SENTINEL = 'SENTINEL-NOT-ECHOED-31337'


@pytest.mark.parametrize('route, payload', [
    ('live-trades', {'start': '2026-09-21'}),                              # date only: no time or offset
    ('live-trades', {'start': '2026-09-21T00:00:00'}),                     # no offset
    ('live-trades', {'start': '2026-09-21 00:00:00Z'}),                    # not RFC 3339's T separator
    ('live-trades', {'start': '2026-09-21T00:00:00.123456Z'}),             # finer than stored milliseconds
    ('live-trades', {'start': '2026-13-01T00:00:00Z'}),
    ('live-trades', {'start': '2026-09-21T00:00:00+24:00'}),
    ('live-trades', {'start': '2026-09-21T00:00:00+05:60'}),
    ('live-trades', {'start': SENTINEL}),
    ('live-trades', {'start': 1790000000000}),                             # ms numbers are not date-times
    ('live-trades', {'start': START, 'end': START}),
    ('live-trades', {'start': END, 'end': START}),
    ('live-trades', {'end': END}),
    ('live-trades', {'recent_days': 3, 'start': START}),
    ('live-trades', {'recent_days': 3, 'end': END}),
    ('live-trades', {'recent_days': True}),
    ('live-trades', {'recent_days': '7'}),
    ('live-trades', {'recent_days': 7.5}),
    ('live-trades', {'recent_days': 7.0}),
    ('live-trades', {'recent_days': 0}),
    ('live-trades', {'recent_days': live_history.MAX_RECENT_DAYS + 1}),
    ('live-trades', {'mode': 'livetrade'}),
    ('live-trades', {'mode': ['live']}),
    ('live-trades', {'mode': SENTINEL}),
    ('live-trades', {'order': 'newest'}),
    ('live-trades', {'limit': 0}),
    ('live-trades', {'limit': live_history.MAX_LIMIT + 1}),
    ('live-trades', {'limit': True}),
    ('live-trades', {'limit': 7.0}),
    ('live-trades', {'limit': '5'}),
    ('live-trades', {'cursor': 'abc', 'recent_days': 3}),                   # a relative window cannot be continued
    ('live-trades', {'cursor': 'abc'}),
    ('live-trades', {'cursor': 'abc', 'start': START}),                     # "until now" moves too
    ('live-trades', {'exchange': SENTINEL * 5}),                           # over 100 characters
    ('live-trades', {'symbol': 42}),
    ('live-trades', {'session_id': SENTINEL}),
    ('live-trades', {'session_id': 12345}),
    ('live-orders', {'time_field': 'updated_at'}),
    ('live-orders', {'status': 'FILLED'}),
    ('live-orders', {'status': SENTINEL}),
])
def test_invalid_selections_are_refused_without_repeating_the_value(api, route, payload):
    body = _post(api, route, payload, 400)
    assert body['error_type'] == 'invalid_request'
    assert SENTINEL not in json.dumps(body)


def test_recent_days_are_anchored_once_to_the_current_time(api, clock):
    session = _session()
    cutoff = NOW - 3 * DAY
    inside = [_trade(session, cutoff), _trade(session, NOW - 1)]
    _trade(session, cutoff - 1)
    _trade(session, NOW)  # the window ends at "now", exclusive
    page = _trades(api, recent_days=3, order='oldest_first')
    assert _ids(page) == inside
    assert page['range'] == {'start': '2026-09-25T12:00:00.000Z', 'end': '2026-09-28T12:00:00.000Z', 'start_ms': cutoff,
                             'end_ms': NOW, 'bounds': 'start inclusive, end exclusive (UTC)', 'source': 'recent_days',
                             'recent_days': 3}


def test_the_default_window_is_the_last_seven_days_and_start_alone_runs_until_now(api):
    session = _session()
    week = [_trade(session, NOW - 7 * DAY), _trade(session, NOW - DAY)]
    _trade(session, NOW - 7 * DAY - 1)
    page = _trades(api, order='oldest_first')
    assert _ids(page) == week
    assert (page['range']['source'], page['range']['recent_days'], page['range']['start_ms']) == (
        'default_recent_days', live_history.DEFAULT_RECENT_DAYS, NOW - 7 * DAY)
    until_now = _trades(api, start='2026-09-27T12:00:00Z')
    assert (until_now['range']['source'], until_now['range']['end_ms']) == ('start_until_now', NOW)
    assert _ids(until_now) == [week[1]]


def _all_pages(api, route: str, **arguments) -> list:
    """Every page of a selection, following next_page exactly as an assistant would."""
    pages = [_post(api, route, arguments)]
    while pages[-1]['next_page']:
        pages.append(_post(api, route, pages[-1]['next_page']))
    return pages


def test_next_page_repeats_the_whole_selection_and_keeps_the_first_window(api, clock):
    session = _session()
    first_five = [_trade(session, NOW - DAY + i * 1000) for i in range(5)]
    first = _trades(api, recent_days=2, limit=2, symbol='BTC-USDT')
    assert (first['total'], first['has_more'], first['all_records_returned']) == (5, True, False)
    replay = first['next_page']
    assert {key: value for key, value in replay.items() if key != 'cursor'} == {
        'start': first['range']['start'], 'end': first['range']['end'], 'mode': 'live', 'exchange': None,
        'symbol': 'BTC-USDT', 'session_id': None, 'order': 'newest_first', 'limit': 2}

    # Time passes and a new trade closes: the next pages still read the original window.
    clock['now'] = NOW + DAY
    _trade(session, NOW + 1000)
    collected = _ids(first)
    while replay:
        page = _trades(api, **replay)
        assert page['total'] == 5 and page['range']['source'] == 'start_end' and page['all_records_returned'] is False
        collected += _ids(page)
        replay = page['next_page']
    assert collected == sorted(first_five, key=lambda tid: first_five.index(tid), reverse=True)
    assert page['has_more'] is False


@pytest.mark.parametrize('order', ['newest_first', 'oldest_first'])
def test_rows_added_or_removed_before_the_cursor_never_shift_later_pages(api, order):
    """Offsets would skip or repeat records here; the keyset cursor continues exactly after the last one."""
    session = _session()
    ids = [_trade(session, START_MS + 10_000 + i * 1000) for i in range(6)]
    first = _trades(api, start=START, end=END, order=order, limit=2)
    seen = _ids(first)
    expected = ids if order == 'oldest_first' else ids[::-1]
    assert seen == expected[:2]
    # Backdated inserts (before the cursor in page order, tied with the cursor's time too) and a
    # deletion of an already returned record.
    before = START_MS + 1000 if order == 'oldest_first' else START_MS + 50_000
    _trade(session, before)
    tie_time = ClosedTrade.get(ClosedTrade.id == seen[-1]).closed_at
    tied = _trade(session, tie_time)
    ClosedTrade.delete().where(ClosedTrade.id == seen[0]).execute()
    rest = _all_pages(api, 'live-trades', **first['next_page'])
    remaining = [tid for page in rest for tid in _ids(page)]
    tied_after = (tied > seen[-1]) if order == 'oldest_first' else (tied < seen[-1])
    # Every original record after the cursor exactly once; a record tied with the cursor's time
    # appears only when its id sorts after the cursor's, like any key after it.
    assert [tid for tid in remaining if tid != tied] == expected[2:]
    assert (tied in remaining) == tied_after


def test_equal_timestamps_page_stably_in_both_orders(api):
    session = _session()
    same = sorted(_trade(session, START_MS + 5) for _ in range(7))
    earlier = _trade(session, START_MS + 4)
    newest = [tid for page in _all_pages(api, 'live-trades', start=START, end=END, limit=3) for tid in _ids(page)]
    assert newest == sorted(same, reverse=True) + [earlier]
    oldest = [tid for page in _all_pages(api, 'live-trades', start=START, end=END, limit=3, order='oldest_first')
              for tid in _ids(page)]
    assert oldest == [earlier] + same
    # The same request returns the same page every time.
    second = _trades(api, **_trades(api, start=START, end=END, limit=3)['next_page'])
    assert _ids(second) == newest[3:6] == _ids(_trades(api, **_trades(api, start=START, end=END, limit=3)['next_page']))


def test_cursors_only_continue_their_own_selection(api):
    session = _session()
    for i in range(4):
        _trade(session, START_MS + i * 1000)
        _order(session, START_MS + i * 1000, status='ACTIVE')
    replay = _trades(api, start=START, end=END, limit=1)['next_page']
    # Changing any part of the selection is refused, never read from the middle.
    for changed in ({'symbol': 'BTC-USDT'}, {'mode': 'all'}, {'exchange': BYBIT}, {'session_id': session},
                    {'order': 'oldest_first'}, {'end': '2026-09-21T23:00:00Z'}, {'start': '2026-09-20T00:00:00Z'}):
        assert _trades(api, 400, **{**replay, **changed})['error_type'] == 'invalid_cursor', changed
    # Dropping a filter of the first page would broaden the selection: refused too.
    narrow = _trades(api, start=START, end=END, limit=1, symbol='BTC-USDT', mode='all')['next_page']
    for dropped in ('symbol', 'mode'):
        assert _trades(api, 400, **{k: v for k, v in narrow.items() if k != dropped})['error_type'] == 'invalid_cursor'
    # The page size may change between pages.
    assert _trades(api, **{**replay, 'limit': 3})['returned'] == 3
    order_replay = _orders(api, start=START, end=END, limit=1, status='ACTIVE')['next_page']
    assert order_replay['status'] == 'ACTIVE' and order_replay['time_field'] == 'created_at'
    for changed in ({'status': None}, {'status': 'CANCELED'}, {'time_field': 'executed_at'}):
        assert _orders(api, 400, **{**order_replay, **changed})['error_type'] == 'invalid_cursor', changed
    # A trades cursor does not continue orders.
    assert _orders(api, 400, **{**order_replay, 'cursor': replay['cursor']})['error_type'] == 'invalid_cursor'
    # Malformed or tampered cursors, without repeating them.
    token = replay['cursor']
    raw = json.loads(base64.urlsafe_b64decode(token + '=' * (-len(token) % 4)))

    def encoded(value) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip('=')

    for bad in (SENTINEL, token + '!', 'A' * (live_history.MAX_CURSOR_CHARS + 1), 12345, True, ['x'],
                encoded({**raw, 't': START_MS - 1}), encoded({**raw, 't': END_MS}), encoded({**raw, 't': True}),
                encoded({**raw, 'id': 'not-a-uuid'}), encoded({**raw, 'v': 2}), encoded({**raw, 'extra': 1}),
                encoded([raw]), encoded({**raw, 'q': '0' * 32})):
        body = _trades(api, 400, **{**replay, 'cursor': bad})
        assert body['error_type'] == 'invalid_cursor' and SENTINEL not in json.dumps(body), bad


# ---------------------------------------------------------------------------
# Scope: sessions, modes, filters
# ---------------------------------------------------------------------------

def test_every_session_is_included_whatever_its_state(api, workers):
    stopped = _session(status='stopped', title='old run')
    running = _session(status='running', title='running now')
    stale = _session(status='running', title='crashed')  # no worker: the dashboard shows it stopped
    deleted = str(uuid.uuid4())                           # trades outlive a deleted session
    workers.add(running)
    trades = {sid: _trade(sid, START_MS + i) for i, sid in enumerate((stopped, running, stale, deleted))}

    page = _trades(api, start=START, end=END, order='oldest_first')
    assert _ids(page) == list(trades.values())
    sessions = page['sessions']
    assert sessions[stopped]['status'] == 'stopped' and sessions[stopped]['title'] == 'old run'
    assert sessions[running]['status'] == 'running' and sessions[running]['is_active'] is True
    assert sessions[stale]['status'] == 'stopped' and sessions[stale]['is_active'] is False
    assert sessions[deleted] == {'exists': False}
    # Reading never writes: the stale row is reported as stopped but left untouched.
    assert LiveSession.get(LiveSession.id == stale).status == 'running'


def test_live_is_the_default_and_paper_must_be_asked_for(api):
    live, paper = _session(), _session(mode='papertrade', title='paper')
    live_trades, paper_trades = [], []
    for i in range(6):
        live_trades.append(_trade(live, START_MS + 2 * i))
        paper_trades.append(_trade(paper, START_MS + 2 * i + 1, mode='papertrade'))

    # Filters are part of the query: a page of 2 holds 2 live trades, and total counts live only.
    page = _trades(api, start=START, end=END, limit=2, order='oldest_first')
    assert _ids(page) == live_trades[:2] and page['total'] == 6
    assert page['filters'] == {'mode': 'live', 'session_modes': ['livetrade'], 'exchange': None, 'symbol': None,
                               'session_id': None}
    assert {item['session_mode'] for item in _trades(api, start=START, end=END, limit=500)['items']} == {'livetrade'}
    assert _ids(_trades(api, start=START, end=END, mode='paper', order='oldest_first')) == paper_trades
    both = _trades(api, start=START, end=END, mode='all', order='oldest_first')
    assert both['total'] == 12 and _ids(both)[:2] == [live_trades[0], paper_trades[0]]
    # Only the exit orders fall in the window (entries are an hour earlier); paper ones need mode.
    assert _orders(api, start=START, end=END)['total'] == 6
    assert _orders(api, start=START, end=END, mode='all')['total'] == 12


def test_exchange_symbol_and_session_filters_match_stored_values_exactly(api):
    one, two = _session(), _session(exchange=BINANCE)
    btc = _trade(one, START_MS + 1)
    eth = _trade(one, START_MS + 2, symbol='ETH-USDT')
    binance = _trade(two, START_MS + 3, exchange=BINANCE)

    def ids(**filters):
        return _ids(_trades(api, start=START, end=END, order='oldest_first', **filters))

    assert ids(exchange=BYBIT) == [btc, eth]
    assert ids(exchange=BINANCE) == [binance]
    assert ids(symbol='BTC-USDT') == [btc, binance]
    assert ids(symbol='ETH-USDT', exchange=BYBIT) == [eth]
    assert ids(session_id=two) == [binance]
    assert ids(session_id=two.upper()) == [binance]  # UUIDs are normalized
    # Exact matching: no substring or case-folding, so the scope is never wider than asked.
    assert ids(symbol='btc-usdt') == [] and ids(symbol='BTC') == [] and ids(exchange='Bybit') == []
    page = _trades(api, start=START, end=END, symbol='ETH-USDT', exchange=BYBIT, session_id=one)
    assert page['filters'] == {'mode': 'live', 'session_modes': ['livetrade'], 'exchange': BYBIT, 'symbol': 'ETH-USDT',
                               'session_id': one}


def test_a_session_of_the_other_mode_is_refused_instead_of_matching_nothing(api):
    paper = _session(mode='papertrade')
    trade = _trade(paper, START_MS, mode='papertrade')
    refused = _trades(api, 400, start=START, end=END, session_id=paper)
    assert refused['error_type'] == 'mode_mismatch' and 'paper' in refused['message']
    assert _orders(api, 400, start=START, end=END, session_id=paper)['error_type'] == 'mode_mismatch'
    assert _ids(_trades(api, start=START, end=END, session_id=paper, mode='paper')) == [trade]
    assert _ids(_trades(api, start=START, end=END, session_id=paper, mode='all')) == [trade]
    live = _session()
    assert _trades(api, 400, start=START, end=END, session_id=live, mode='paper')['error_type'] == 'mode_mismatch'


# ---------------------------------------------------------------------------
# Trade and order values
# ---------------------------------------------------------------------------

def test_only_closed_trades_are_returned_and_open_ones_are_counted(api):
    session = _session()
    closed = _trade(session, START_MS + 10)
    _trade(session, None, opened_at=START_MS + 20)              # still open, opened inside the window
    _trade(session, None, opened_at=END_MS + 5)                 # opened after the window: not counted
    _trade(session, START_MS + 30, soft_deleted=True)           # merged/discarded by the plugin
    _trade(session, None, opened_at=START_MS, soft_deleted=True)
    paper = _session(mode='papertrade')
    _trade(paper, None, opened_at=START_MS, mode='papertrade')  # other mode: not counted either

    page = _trades(api, start=START, end=END)
    assert _ids(page) == [closed]
    assert page['open_trades_not_included'] == 1
    assert 'Open trades are not included' in page['note']
    assert _trades(api, start=START, end=END, mode='all')['open_trades_not_included'] == 2


def test_trade_values_are_the_dashboards(api):
    session = _session()
    long_id = _trade(session, START_MS + 3_600_000, entry=100, exit=110, qty=2, fees=(0.1, 0.2), leverage=2)
    short_id = _trade(session, START_MS + 7_200_000, kind='short', entry=50, exit=45, qty=4, fees=(0.3, None))
    # A cancelled order of the trade never counts toward its values.
    _order(session, START_MS + 60_000, trade_id=long_id, side='sell', qty=-5, price=1, status='CANCELED',
           canceled_at=START_MS + 90_000)

    items = {item['id']: item for item in _trades(api, start=START, end=END)['items']}
    for trade_id in (long_id, short_id):
        expected = get_closed_trade_details(populate_order_arrays(ClosedTrade.get(ClosedTrade.id == trade_id)))
        item = items[trade_id]
        for field in ('entry_price', 'exit_price', 'qty', 'pnl', 'pnl_percentage', 'fee', 'size', 'leverage',
                      'opened_at', 'closed_at', 'symbol', 'exchange', 'type', 'timeframe', 'strategy_name'):
            assert item[field] == pytest.approx(expected[field]) if isinstance(item[field], float) else item[field] == expected[field], field
        assert item['holding_period_seconds'] == expected['holding_period']
    assert items[long_id]['pnl'] == pytest.approx(2 * 10 - 0.3)
    assert items[short_id]['pnl'] == pytest.approx(4 * 5 - 0.3)
    assert (items[long_id]['executed_orders'], items[long_id]['orders_without_fee']) == (2, 0)
    assert (items[short_id]['executed_orders'], items[short_id]['orders_without_fee']) == (2, 1)
    assert items[long_id]['session_id'] == session and items[long_id]['session_mode'] == 'livetrade'


def test_orders_by_creation_or_execution_time_keep_their_status_and_timestamps(api):
    session = _session()
    before = START_MS - 60_000
    filled_later = _order(session, before, executed_at=START_MS + 1, fee=0.5, exchange_id='ex-1')
    cancelled = _order(session, START_MS + 2, status='CANCELED', canceled_at=START_MS + 3)
    active = _order(session, START_MS + 4, status='ACTIVE')
    partial = _order(session, START_MS + 5, status='PARTIALLY FILLED')
    found = _order(session, START_MS + 6, executed_at=START_MS + 6, jesse_submitted=False)

    created = _orders(api, start=START, end=END, order='oldest_first')
    assert _ids(created) == [cancelled, active, partial, found]
    assert created['counts_by_status'] == {'ACTIVE': 1, 'CANCELED': 1, 'EXECUTED': 1, 'PARTIALLY FILLED': 1}
    items = {item['id']: item for item in created['items']}
    assert (items[cancelled]['status'], items[cancelled]['canceled_at'], items[cancelled]['executed_at']) == (
        'CANCELED', START_MS + 3, None)
    assert (items[active]['executed_at'], items[active]['canceled_at']) == (None, None)
    assert items[found]['jesse_submitted'] is False and items[cancelled]['jesse_submitted'] is True
    assert 'created_at' in created['note'] and created['filters']['time_field'] == 'created_at'

    executed = _orders(api, start=START, end=END, time_field='executed_at', order='oldest_first')
    assert _ids(executed) == [filled_later, found]  # created before the window, executed inside it
    assert executed['items'][0]['created_at'] == before and executed['items'][0]['fee'] == 0.5
    assert executed['items'][0]['exchange_id'] == 'ex-1'
    assert _ids(_orders(api, start=START, end=END, status='partially_filled')) == [partial]
    assert _orders(api, start=START, end=END, status='partially filled')['filters']['status'] == 'PARTIALLY FILLED'
    assert _ids(_orders(api, start=START, end=END, status='canceled')) == [cancelled]


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

def test_each_record_is_redacted_with_its_own_sessions_keys(api):
    one = _session(key=KEY_A, notification=TELEGRAM, title=f'bybit {FAKE_KEY_A}')
    two = _session(key=KEY_B, exchange=BINANCE)
    deleted = str(uuid.uuid4())
    _order(one, START_MS + 1, status='ACTIVE', exchange_id=f'{FAKE_SECRET_A}|{FAKE_PASSPHRASE_A}|{FAKE_BOT_TOKEN}')
    _order(two, START_MS + 2, status='ACTIVE', exchange_id=f'id-{FAKE_SECRET_B}', exchange=BINANCE)
    _order(deleted, START_MS + 3, status='ACTIVE', exchange_id=f'{FAKE_KEY_A}/{FAKE_KEY_B}')

    page = _orders(api, start=START, end=END, order='oldest_first')
    _no_fakes(page)
    assert [item['exchange_id'] for item in page['items']] == [
        '[redacted]|[redacted]|[redacted]', 'id-[redacted]', '[redacted]/[redacted]']
    assert page['sessions'][one]['title'] == 'bybit [redacted]'
    assert page['sessions'][deleted] == {'exists': False}


def test_a_failed_key_lookup_returns_nothing(api, monkeypatch):
    session = _session(key=KEY_A)
    _trade(session, START_MS + 1)

    def broken(*_args, **_kwargs):
        raise RuntimeError(f'database went away: {FAKE_SECRET_A}')

    monkeypatch.setattr(ExchangeApiKeys, 'get_or_none', broken)
    for route in ('live-trades', 'live-orders'):
        body = _post(api, route, {'start': START, 'end': END}, 500)
        assert body['error_type'] == 'read_failed' and 'items' not in body
        _no_fakes(body)


def test_unknown_keys_of_deleted_sessions_fail_closed_too(api, monkeypatch):
    _trade(str(uuid.uuid4()), START_MS + 1)

    def broken(*_args, **_kwargs):
        raise RuntimeError('database went away')

    monkeypatch.setattr(ExchangeApiKeys, 'select', broken)
    body = _trades(api, 500, start=START, end=END)
    assert body['error_type'] == 'read_failed' and 'items' not in body


def test_an_unreadable_session_state_fails_the_read(api):
    session = _session(state='{not json')
    _trade(session, START_MS + 1)
    body = _trades(api, 500, start=START, end=END)
    assert body['error_type'] == 'read_failed' and session in body['message'] and 'items' not in body


# ---------------------------------------------------------------------------
# Empty results and bounds
# ---------------------------------------------------------------------------

def test_empty_history_is_reported_as_such(api):
    for page in (_trades(api, recent_days=3), _orders(api, recent_days=3)):
        assert (page['items'], page['total'], page['returned'], page['has_more']) == ([], 0, 0, False)
        assert (page['all_records_returned'], page['next_page'], page['sessions']) == (True, None, {})
        assert "Not the exchange account's history" in page['source']
    assert _trades(api, recent_days=3)['open_trades_not_included'] == 0
    assert _orders(api, recent_days=3)['counts_by_status'] == {}


def test_pages_are_bounded_by_limit_and_payload_size(api, monkeypatch):
    session = _session()
    all_ids = [_trade(session, START_MS + i) for i in range(12)]
    full = _trades(api, start=START, end=END, limit=live_history.MAX_LIMIT)
    assert full['returned'] == 12 and full['all_records_returned'] is True

    monkeypatch.setattr(live_history, 'MAX_RESPONSE_BYTES', 8 * 1024)
    pages = _all_pages(api, 'live-trades', start=START, end=END, limit=10, order='oldest_first')
    for page in pages:
        # The whole response, as the MCP client receives it, fits (with the transport allowance).
        assert live_history._wire_bytes(page) <= 8 * 1024 - live_history.TRANSPORT_ALLOWANCE
    assert [tid for page in pages for tid in _ids(page)] == all_ids  # created in closing order
    assert len(pages) > 2 and all(page['truncated_by_size'] for page in pages[:-1])


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------

def test_mcp_tools_return_the_route_results(api, tools):
    session = _session(key=KEY_A)
    trade = _trade(session, NOW - DAY)
    result = tools['get_live_trades'](recent_days=3)
    assert result['status'] == 'success' and result['action'] == 'get_live_trades'
    assert _ids(result) == [trade] and result['range']['source'] == 'recent_days'
    orders = tools['get_live_orders'](recent_days=3, time_field='executed_at')
    assert orders['total'] == 2 and orders['filters']['time_field'] == 'executed_at'
    refused = tools['get_live_trades'](start='2026-09-21')
    assert refused['error_type'] == 'invalid_request' and 'RFC 3339' in refused['message']
    _no_fakes(result)
    _no_fakes(orders)


def test_real_fastmcp_keeps_recent_days_strict_and_advertises_its_type(api, tools):
    session = _session()
    trade = _trade(session, NOW - DAY)
    server = mcp_server.create_mcp_server(0)
    schemas = {tool.name: tool.inputSchema for tool in asyncio.run(server.list_tools())}
    for name in ('get_live_trades', 'get_live_orders'):
        properties = schemas[name]['properties']
        assert properties['recent_days']['anyOf'] == [{'type': 'integer', 'minimum': 1, 'maximum': 366}, {'type': 'null'}]
        assert properties['mode']['enum'] == ['live', 'paper', 'all'] and properties['limit']['maximum'] == 500
        assert properties['cursor']['anyOf'] == [{'type': 'string'}, {'type': 'null'}] and 'offset' not in properties
        assert properties['mode']['default'] == 'live' and properties['limit']['default'] == 100
        assert 'required' not in schemas[name]

    def call(arguments):
        result = asyncio.run(server.call_tool('get_live_trades', arguments))
        contents = result[0] if isinstance(result, tuple) else result
        return json.loads(contents[0].text)

    # pydantic would have coerced these (true -> 1, "7" -> 7, 7.9 -> 7) or refused them with an
    # error quoting the value; the service refuses them without repeating it.
    for arguments in ({'recent_days': True}, {'recent_days': '7'}, {'limit': True}, {'limit': 7.9}, {'limit': '5'},
                      {'symbol': 5}, {'symbol': {'nested': SENTINEL}}, {'start': 1790000000000},
                      {'mode': SENTINEL}, {'order': [SENTINEL]}, {'session_id': 42}, {'cursor': 7}):
        result = asyncio.run(server.call_tool('get_live_trades', arguments))
        contents = result[0] if isinstance(result, tuple) else result
        text = contents[0].text
        assert json.loads(text)['error_type'] in ('invalid_request', 'invalid_cursor'), arguments
        assert SENTINEL not in text and 'input_value' not in text and 'validation error' not in text, arguments
    assert call({'recent_days': 2, 'limit': 1})['returned'] == 1
    assert [item['id'] for item in call({'recent_days': 2})['items']] == [trade]


# ---------------------------------------------------------------------------
# Analysis datasets
# ---------------------------------------------------------------------------

def _run(api, code: str, inputs: list, expect: int = 200) -> dict:
    response = api.post('/analysis/run', json={'code': code, 'inputs': inputs, 'timeout_minutes': 5}, headers=HEADERS)
    assert response.status_code == expect, response.text
    return response.json()


def _wait(api, job_id: str) -> dict:
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        body = api.post('/analysis/jobs', json={'job_id': job_id, 'tail_lines': 200}, headers=HEADERS).json()
        if body['job']['status'] != 'running':
            return body
        time.sleep(0.05)
    raise AssertionError(f'analysis job {job_id} did not finish')


def _no_workspaces(project: Path) -> bool:
    root = project / 'storage' / 'mcp' / 'analysis'
    return not root.exists() or not any(path.name for path in root.iterdir() if not path.name.startswith('.trash-'))


CHART_CODE = '''
import json
import matplotlib.pyplot as plt

data = json.load(open("inputs/trades.json"))
manifest = json.load(open("inputs/manifest.json"))
trades = data["trades"]
keys = [(t["closed_at"], t["id"]) for t in trades]
assert keys == sorted(keys), "oldest first"
assert data["count"] == len(trades) and data["complete"] is True
assert manifest[0]["count"] == len(trades)
print("count", len(trades), "range", data["range"]["start"], data["range"]["end"])
print("ids", ",".join(t["id"] for t in trades))
print("sessions", sorted(data["sessions"]))
total = 0.0
points = []
for t in trades:
    total += t["pnl"]
    points.append(total)
fig, ax = plt.subplots(figsize=(5, 3))
ax.step(range(len(points)), points, where="post")
fig.savefig("output/cumulative_pnl.png", dpi=80)
plt.close(fig)
'''


def test_a_dataset_snapshot_holds_every_record_and_its_chart_comes_back_as_an_image(api, tools, project, monkeypatch):
    # Small batches, so the snapshot is streamed in many keyset pages across equal timestamps.
    monkeypatch.setattr(live_history, 'BATCH_SIZE', 4)
    one, two, paper = _session(key=KEY_A, title='one'), _session(key=KEY_B, title='two'), _session(mode='papertrade')
    expected = []
    for i in range(15):
        expected.append(_trade(one if i % 2 else two, START_MS + (i // 3) * 1000))  # threes share a timestamp
        _trade(paper, START_MS + i, mode='papertrade')
    _trade(one, END_MS)  # outside

    discovered = tools['get_live_trades'](start=START, end=END, limit=5)
    assert discovered['total'] == 15 and discovered['all_records_returned'] is False

    server = mcp_server.create_mcp_server(0)
    started = asyncio.run(server.call_tool('run_analysis', {'code': CHART_CODE, 'inputs': [
        {'dataset': 'live_trades', 'name': 'trades', 'start': discovered['range']['start'],
         'end': discovered['range']['end']},
    ]}))
    contents = started[0] if isinstance(started, tuple) else started
    job = json.loads(contents[0].text)['job']
    [entry] = job['inputs']
    assert (entry['dataset'], entry['count'], entry['file']) == ('live_trades', 15, 'inputs/trades.json')
    assert (entry['range']['start_ms'], entry['range']['end_ms']) == (START_MS, END_MS)
    assert entry['filters']['mode'] == 'live'

    finished = _wait(api, job['id'])
    assert finished['job']['status'] == 'succeeded', finished['output']
    ids_line = next(line for line in finished['output'].splitlines() if line.startswith('ids '))
    assert ids_line[4:].split(',') == sorted(expected, key=lambda tid: (ClosedTrade.get(ClosedTrade.id == tid).closed_at, tid))
    assert f"sessions {sorted([one, two])}" in finished['output']
    snapshot = (project / 'storage' / 'mcp' / 'analysis' / job['id'] / 'inputs' / 'trades.json').read_text()
    _no_fakes(snapshot)

    result = asyncio.run(server.call_tool('get_analysis_artifact', {'job_id': job['id'], 'path': 'cumulative_pnl.png'}))
    assert isinstance(result, CallToolResult) and not result.isError
    text, image = result.content
    assert isinstance(text, TextContent) and isinstance(image, ImageContent)
    assert base64.b64decode(image.data).startswith(b'\x89PNG')


def test_order_datasets_are_redacted_and_keep_status_counts(api, project):
    session = _session(key=KEY_A)
    _order(session, START_MS + 1, status='ACTIVE', exchange_id=f'x-{FAKE_SECRET_A}')
    _order(session, START_MS + 2, status='CANCELED', canceled_at=START_MS + 3)
    _order(session, START_MS - 5, executed_at=START_MS + 4)
    code = ('import json\nd = json.load(open("inputs/orders.json"))\n'
            'print("orders", [o["status"] for o in d["orders"]], d["counts_by_status"], d["filters"]["time_field"])\n')
    job = _run(api, code, [{'dataset': 'live_orders', 'name': 'orders', 'start': START, 'end': END}])['job']
    finished = _wait(api, job['id'])
    assert finished['job']['status'] == 'succeeded', finished['output']
    assert "orders ['ACTIVE', 'CANCELED'] {'ACTIVE': 1, 'CANCELED': 1} created_at" in finished['output']
    snapshot = (project / 'storage' / 'mcp' / 'analysis' / job['id'] / 'inputs' / 'orders.json').read_text()
    assert 'x-[redacted]' in snapshot
    _no_fakes(snapshot)


def test_an_empty_window_gives_an_empty_complete_snapshot(api):
    code = ('import json\nd = json.load(open("inputs/live_trades.json"))\n'
            'print("empty", d["count"], d["trades"], d["complete"], d["open_trades_not_included"])\n')
    job = _run(api, code, [{'dataset': 'live_trades', 'recent_days': 3}])['job']
    assert job['inputs'][0]['count'] == 0 and job['inputs'][0]['name'] == 'live_trades'
    finished = _wait(api, job['id'])
    assert 'empty 0 [] True 0' in finished['output']


def test_oversized_selections_are_refused_not_cut(api, project, monkeypatch):
    session = _session()
    for i in range(4):
        _trade(session, START_MS + i)
    inputs = [{'dataset': 'live_trades', 'start': START, 'end': END}]
    monkeypatch.setattr(live_history, 'MAX_ANALYSIS_TRADES', 3)
    body = _run(api, 'print(1)', inputs, 413)
    assert body['error_type'] == 'too_many_records' and '4 trades' in body['message'] and 'limited to 3' in body['message']
    assert _no_workspaces(project)

    # Rows that appear while the snapshot streams are counted too; the run is refused, not cut.
    monkeypatch.setattr(live_history, 'MAX_ANALYSIS_TRADES', 4)
    monkeypatch.setattr(live_history, 'BATCH_SIZE', 2)
    real_records = live_history._trade_records
    added = []

    def records_then_insert(trades):
        if not added:
            added.extend(_trade(session, START_MS + 100 + i) for i in range(2))
        return real_records(trades)

    monkeypatch.setattr(live_history, '_trade_records', records_then_insert)
    body = _run(api, 'print(1)', inputs, 413)
    assert body['error_type'] == 'too_many_records' and '6 trades' in body['message']
    assert _no_workspaces(project)

    monkeypatch.setattr(live_history, '_trade_records', real_records)
    monkeypatch.setattr(live_history, 'MAX_ANALYSIS_TRADES', 100)
    monkeypatch.setattr(analysis_jobs, 'MAX_INPUT_BYTES', 1500)
    body = _run(api, 'print(1)', inputs, 413)
    assert body['error_type'] == 'too_large' and 'live_trades snapshot' in body['message']
    assert _no_workspaces(project)


@pytest.mark.parametrize('item, error_type', [
    ({'dataset': 'live_trades', 'recent_day': 7}, 'invalid_request'),           # misspelled filter
    ({'dataset': 'live_trades', 'time_field': 'executed_at'}, 'invalid_request'),  # an orders-only filter
    ({'dataset': 'live_trades', 'session_type': 'live'}, 'invalid_request'),
    ({'dataset': 'trades'}, 'invalid_request'),
    ({'dataset': 'live_trades', 'start': '2026-09-21'}, 'invalid_request'),
    ({'dataset': 'live_trades', 'recent_days': '7'}, 'invalid_request'),
    ({'dataset': 'live_orders', 'status': 'FILLED'}, 'invalid_request'),
    ({'dataset': 'live_trades', 'name': '../x'}, 'invalid_request'),
])
def test_dataset_inputs_are_validated_before_any_workspace_exists(api, project, item, error_type):
    body = _run(api, 'print(1)', [item], 400)
    assert body['error_type'] == error_type
    assert _no_workspaces(project)


def test_dataset_and_session_inputs_combine_and_names_stay_unique(api):
    paper = _session(mode='papertrade')
    body = _run(api, 'print(1)', [{'dataset': 'live_trades', 'session_id': paper}], 400)
    assert body['error_type'] == 'mode_mismatch'
    duplicate = _run(api, 'print(1)', [{'dataset': 'live_trades'}, {'dataset': 'live_trades'}], 400)
    assert 'used twice' in duplicate['message']
    job = _run(api, 'import json\nprint(sorted(e["name"] for e in json.load(open("inputs/manifest.json"))))\n',
               [{'dataset': 'live_trades', 'name': 'week'}, {'dataset': 'live_orders', 'name': 'orders', 'recent_days': 1},
                {'dataset': 'live_trades', 'name': 'paper', 'mode': 'paper', 'session_id': paper}])['job']
    assert [entry['range']['source'] for entry in job['inputs']] == ['default_recent_days', 'recent_days', 'default_recent_days']
    assert _wait(api, job['id'])['output'].strip().endswith("['orders', 'paper', 'week']")


# ---------------------------------------------------------------------------
# Guidance
# ---------------------------------------------------------------------------

def test_guidance_describes_the_workflow_and_its_limits():
    rules = _load_packaged_rules()
    assert '`get_live_trades` / `get_live_orders`' in rules
    assert "not the exchange account's history" in rules
    assert 'Never compute totals, win rates, or other statistics from a partial page' in rules
    assert 'never mix them into real performance' in rules
    mcp = FakeMCP()
    register_resources(mcp)
    guide = mcp.resources['jesse://session_analysis']()
    assert 'Workflow: "analyze my trades of the last 7 days"' in guide
    assert '`total` is 0' in guide and 'too_many_records' in guide and 'open_trades_not_included' in guide
    assert 'get_live_trades' in mcp.resources['jesse://live_trading']()
    register_tools(mcp)
    for name in ('get_live_trades', 'get_live_orders'):
        doc = mcp.tools[name].__doc__
        assert "NOT the exchange account's history" in doc and 'start inclusive, end exclusive' in doc
        assert 'next_page' in doc and 'mode "live" (default' in doc
    assert '"dataset": "live_trades"' in mcp.tools['run_analysis'].__doc__
    assert 'get_live_trades' in mcp_server.INSTRUCTIONS


def test_the_documented_limits_hold_and_a_full_snapshot_fits_its_byte_cap(api):
    assert (live_history.DEFAULT_RECENT_DAYS, live_history.MAX_RECENT_DAYS) == (7, 366)
    assert (live_history.DEFAULT_LIMIT, live_history.MAX_LIMIT) == (100, 500)
    assert live_history.MAX_ANALYSIS_TRADES == live_history.MAX_ANALYSIS_ORDERS == 100_000
    # The largest realistic records (long exchange name, symbol, strategy, exchange order ID) at
    # the row cap must stay under the snapshot byte cap, or the cap would never be reached.
    session = _session(exchange='Binance Perpetual Futures')
    trade_id = _trade(session, START_MS + 123_456, symbol='1000SHIB-USDT', exchange='Binance Perpetual Futures',
                      kind='short', entry=61234.567890123, exit=61200.123456789, qty=0.123456789012, leverage=10)
    _order(session, START_MS + 1, trade_id=trade_id, status='PARTIALLY FILLED', exchange='Binance Perpetual Futures',
           symbol='1000SHIB-USDT', exchange_id='1234567890123456789-abcdef-0123456789', canceled_at=START_MS + 2,
           fee=3.0254567890123, qty=-0.123456789012, price=61234.567890123, mode='livetrade')
    trade = _trades(api, start=START, end=END)['items'][0]
    order = next(item for item in _orders(api, start=START, end=END)['items'] if item['status'] == 'PARTIALLY FILLED')
    for record, cap in ((trade, live_history.MAX_ANALYSIS_TRADES), (order, live_history.MAX_ANALYSIS_ORDERS)):
        padded = {**record, 'strategy_name': 'MyTrendFollowingStrategy'} if 'strategy_name' in record else record
        size = len(json.dumps(padded, separators=(',', ':'))) + 1
        assert size * cap < analysis_jobs.MAX_INPUT_BYTES - 64 * 1024, (size, cap)


# ---------------------------------------------------------------------------
# Round 1 review: unknown fields, calendar edges, complete live snapshots, dashboard values
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('route, extra', [
    ('live-trades', {'recent_day': 3}),                 # misspelled window: would fall back to 7 days
    ('live-trades', {'symbl': SENTINEL}),               # misspelled filter: would widen to every symbol
    ('live-trades', {'time_field': 'executed_at'}),     # an orders-only field
    ('live-trades', {'status': 'EXECUTED'}),
    ('live-orders', {'recent_day': 3}),
    ('live-orders', {'exchnage': SENTINEL}),
    ('live-orders', {SENTINEL: 1}),
])
def test_routes_refuse_unknown_fields_without_repeating_them(api, route, extra):
    session = _session()
    _trade(session, NOW - DAY)
    body = _post(api, route, {'recent_days': 3, **extra}, 400)
    dataset = 'live_trades' if route == 'live-trades' else 'live_orders'
    accepted = ', '.join(live_history.PARAMS[dataset] + live_history.PAGE_PARAMS)
    # The exact text: only the accepted names, never the given name or value.
    assert body == {'status': 'error', 'error_type': 'invalid_request',
                    'message': f'Unknown field(s) in the request; {dataset} accepts only: {accepted}.'}
    # Without the extra field the same request succeeds.
    assert _post(api, route, {'recent_days': 3})['total'] > 0


def test_fastmcp_refuses_unknown_arguments_before_any_request(api, tools, monkeypatch):
    session = _session()
    trade = _trade(session, NOW - DAY)
    server = mcp_server.create_mcp_server(0)
    requests_seen = []
    forward = project_files_service.requests.post

    def recording_post(url, json=None, headers=None, timeout=None):
        requests_seen.append(url)
        return forward(url, json=json, headers=headers, timeout=timeout)

    monkeypatch.setattr(project_files_service.requests, 'post', recording_post)

    def call(name, arguments):
        result = asyncio.run(server.call_tool(name, arguments))
        contents = result[0] if isinstance(result, tuple) else result
        return json.loads(contents[0].text)

    for name, arguments in (('get_live_trades', {'recent_day': 3}), ('get_live_trades', {'symbl': SENTINEL}),
                            ('get_live_trades', {'time_field': 'executed_at'}),
                            ('get_live_orders', {'recent_days': 3, 'statuss': 'EXECUTED'})):
        refused = call(name, arguments)
        extra = ', time_field, status' if name == 'get_live_orders' else ''
        assert refused == {'status': 'error', 'action': name, 'error_type': 'invalid_request', 'message': (
            f'Unknown argument(s); {name} accepts only: start, end, recent_days, mode, exchange, symbol, session_id'
            f'{extra}, order, cursor, limit.')}
    assert requests_seen == []
    assert [item['id'] for item in call('get_live_trades', {'recent_days': 3})['items']] == [trade]
    assert call('get_live_orders', {'recent_days': 3, 'status': 'EXECUTED'})['total'] == 2
    # The advertised schemas are unchanged: no extra properties are announced or allowed in them.
    schemas = {tool.name: tool.inputSchema for tool in asyncio.run(server.list_tools())}
    for name in ('get_live_trades', 'get_live_orders'):
        assert 'additionalProperties' not in schemas[name] and 'recent_day' not in schemas[name]['properties']


@pytest.mark.parametrize('start, end', [
    ('0001-01-01T00:00:00+00:01', None),                # normalizes to year 0
    ('0001-01-01T00:00:00+23:59', '2026-09-22T00:00:00Z'),
    ('2026-09-21T00:00:00Z', '9999-12-31T23:59:59-00:01'),  # normalizes to year 10000
    ('9999-12-31T23:59:59.999-23:59', None),
    ('0000-12-31T23:59:59Z', None),
    ('2026-02-29T00:00:00Z', None),                     # not a leap year
    ('2026-09-21T24:00:00Z', None),
])
def test_calendar_edges_are_refused_cleanly(api, start, end):
    body = _trades(api, 400, start=start, **({'end': end} if end else {}))
    assert body['error_type'] == 'invalid_request' and 'valid date-time' in body['message']


def test_the_widest_representable_window_works(api):
    session = _session()
    trade = _trade(session, START_MS)
    widest = _trades(api, start='0001-01-01T00:00:00Z', end='9999-12-31T23:59:59.999Z')
    assert (widest['range']['start'], widest['range']['end']) == ('0001-01-01T00:00:00.000Z', '9999-12-31T23:59:59.999Z')
    assert _ids(widest) == [trade]
    shifted = _trades(api, start='0001-01-01T00:00:00-01:00', end='9999-12-31T23:59:59.999+01:00')
    assert (shifted['range']['start'], shifted['range']['end']) == ('0001-01-01T01:00:00.000Z', '9999-12-31T22:59:59.999Z')


def _equity(session_id: str, count: int) -> None:
    for i in range(count):
        LiveEquitySnapshot.create(session_id=session_id, timestamp=START_MS + i * 60_000, currency='USDT', equity=1000.0 + i)


def _live_input(session_id: str) -> list:
    return [{'session_type': 'live', 'session_id': session_id, 'name': 'live'}]


@pytest.mark.parametrize('cap, section', [
    ('MAX_EXPORT_LIVE_TRADES', 'closed trades'),
    ('MAX_EXPORT_LIVE_ORDERS', 'orders'),
    ('MAX_EXPORT_LIVE_EQUITY_POINTS', 'equity curve'),
])
def test_a_live_session_over_any_snapshot_cap_is_refused_not_cut(api, project, monkeypatch, cap, section):
    session = _session(key=KEY_A)
    for i in range(3):
        _trade(session, START_MS + i)          # 3 trades, 6 orders
    _equity(session, 4)
    sizes = {'MAX_EXPORT_LIVE_TRADES': 3, 'MAX_EXPORT_LIVE_ORDERS': 6, 'MAX_EXPORT_LIVE_EQUITY_POINTS': 4}
    for name, size in sizes.items():
        monkeypatch.setattr(session_results, name, size)
    monkeypatch.setattr(session_results, cap, sizes[cap] - 1)
    loaded = []
    for loader in ('_live_trades', '_live_orders', '_live_equity'):
        real = getattr(session_results, loader)
        monkeypatch.setattr(session_results, loader,
                            lambda *args, _real=real, _name=loader: loaded.append(_name) or _real(*args))

    body = _run(api, 'print(1)', _live_input(session), 413)
    assert loaded == []  # refused from the counts, before any rows were read
    assert body['error_type'] == 'too_many_records' and section in body['message']
    assert f'has {sizes[cap]} {section} rows' in body['message'] and f'limited to {sizes[cap] - 1}' in body['message']
    assert _no_workspaces(project)
    _no_fakes(body)
    # Paging one session is unaffected by the snapshot caps.
    page = api.post('/session-results/get', headers=HEADERS, json={
        'session_type': 'live', 'session_id': session, 'section': 'closed_trades', 'limit': 50}).json()
    assert page['total'] == 3 and page['returned'] == 3


def test_a_live_session_at_its_caps_is_exported_completely(api, monkeypatch):
    session = _session(key=KEY_A)
    for i in range(3):
        _trade(session, START_MS + i)
    _order(session, START_MS + 10, status='ACTIVE', exchange_id=f'x-{FAKE_SECRET_A}')
    _equity(session, 4)
    for name, size in (('MAX_EXPORT_LIVE_TRADES', 3), ('MAX_EXPORT_LIVE_ORDERS', 7), ('MAX_EXPORT_LIVE_EQUITY_POINTS', 4)):
        monkeypatch.setattr(session_results, name, size)
    code = ('import json\nd = json.load(open("inputs/live.json"))\n'
            'print("sizes", len(d["closed_trades"]), len(d["orders"]), len(d["equity_curve"]), d["complete"], "truncated" in d)\n')
    job = _run(api, code, _live_input(session))['job']
    finished = _wait(api, job['id'])
    assert 'sizes 3 7 4 True False' in finished['output'], finished['output']
    _no_fakes((Path('storage/mcp/analysis') / job['id'] / 'inputs' / 'live.json').read_text())


def test_rows_added_after_the_cap_check_still_refuse_the_live_snapshot(api, project, monkeypatch):
    session = _session()
    for i in range(3):
        _trade(session, START_MS + i)
    monkeypatch.setattr(session_results, 'MAX_EXPORT_LIVE_ORDERS', 6)
    real_orders = session_results._live_orders

    def orders_after_an_insert(session_id, offset, limit):
        _order(session, START_MS + 100, status='ACTIVE')  # lands between the counts and the read
        return real_orders(session_id, offset, limit)

    monkeypatch.setattr(session_results, '_live_orders', orders_after_an_insert)
    body = _run(api, 'print(1)', _live_input(session), 413)
    assert body['error_type'] == 'too_many_records' and 'has 7 orders rows' in body['message']
    assert _no_workspaces(project)


def _dashboard_trade(api, trade_id: str) -> dict:
    response = api.get(f'/closed-trades/{trade_id}', headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()['data']


DASHBOARD_FIELDS = ('entry_price', 'exit_price', 'qty', 'pnl', 'pnl_percentage', 'fee', 'size', 'leverage',
                    'opened_at', 'closed_at', 'symbol', 'exchange', 'type', 'timeframe', 'strategy_name')


def _assert_dashboard_values(record: dict, dashboard: dict) -> None:
    for field in DASHBOARD_FIELDS:
        if isinstance(dashboard[field], float):
            assert record[field] == pytest.approx(dashboard[field], rel=1e-12, abs=1e-12), field
        else:
            assert record[field] == dashboard[field], field
    assert record['holding_period_seconds'] == dashboard['holding_period']


def test_scaled_continued_and_merged_trades_match_the_dashboard_routes(api):
    first, later = _session(key=KEY_A, title='first'), _session(title='continued')
    # Scaled in over two sessions (a persistent live trade continued by a later session), scaled
    # out in two exits, with a cancelled and a partially filled order that must not count.
    scaled = str(uuid.uuid4())
    ClosedTrade.create(id=scaled, session_id=first, strategy_name='Demo', symbol='BTC-USDT', exchange=BYBIT, type='long',
                       timeframe='1h', opened_at=START_MS, closed_at=START_MS + 5_000, leverage=3, created_at=START_MS,
                       updated_at=START_MS, session_mode='livetrade')
    for owner, side, qty, price, at, fee in ((first, 'buy', 1.0, 100.0, START_MS, 0.1),
                                             (first, 'buy', 2.0, 103.0, START_MS + 1_000, None),
                                             (later, 'buy', 1.5, 98.0, START_MS + 1_000, 0.07),
                                             (later, 'sell', -2.0, 110.0, START_MS + 4_000, 0.2),
                                             (later, 'sell', -2.5, 112.5, START_MS + 5_000, 0.3)):
        _order(owner, at, trade_id=scaled, side=side, qty=qty, price=price, executed_at=at, fee=fee)
    _order(later, START_MS + 2_000, trade_id=scaled, side='sell', qty=-4.5, price=150.0, status='CANCELED',
           canceled_at=START_MS + 3_000)
    _order(later, START_MS + 2_500, trade_id=scaled, side='sell', qty=-1.0, price=140.0, status='PARTIALLY FILLED')

    # Merged: the plugin moved a discarded trade's orders onto the surviving short trade.
    survivor = _trade(first, START_MS + 9_000, kind='short', entry=50.0, exit=45.0, qty=2.0, fees=(0.05, 0.05))
    discarded = _trade(first, START_MS + 8_000, kind='short', entry=52.0, exit=45.0, qty=1.0, fees=(0.02, 0.02),
                       soft_deleted=True)
    Order.update(trade_id=survivor).where(Order.trade_id == discarded).execute()

    items = {item['id']: item for item in _trades(api, start=START, end=END)['items']}
    assert set(items) == {scaled, survivor}
    for trade_id in (scaled, survivor):
        _assert_dashboard_values(items[trade_id], _dashboard_trade(api, trade_id))
    assert items[scaled]['entry_price'] == pytest.approx((1 * 100 + 2 * 103 + 1.5 * 98) / 4.5)
    assert (items[scaled]['executed_orders'], items[scaled]['orders_without_fee']) == (5, 1)
    assert items[scaled]['session_id'] == first
    assert (items[survivor]['qty'], items[survivor]['executed_orders']) == (3.0, 4)
    # The dashboard's list route agrees on the values it shows.
    listed = api.get(f'/closed-trades/list?session_id={first}&limit=10', headers=HEADERS).json()['data']
    for row in listed:
        if row['id'] in items and row['status'] == 'closed':
            for field in ('entry_price', 'exit_price', 'qty', 'pnl', 'pnl_percentage'):
                assert items[row['id']][field] == pytest.approx(row[field], rel=1e-12), field


def test_a_snapshot_of_many_multi_order_trades_matches_the_dashboard(api, project, monkeypatch):
    # Small batches so keyset pages and the per-batch order query cross trade boundaries often.
    monkeypatch.setattr(live_history, 'BATCH_SIZE', 4)
    rng = random.Random(7)
    sessions = [_session(key=KEY_A), _session(key=KEY_B, exchange=BINANCE), _session()]
    trade_ids = []
    for i in range(30):
        owner = sessions[i % 3]
        kind = 'long' if i % 2 else 'short'
        trade_id = str(uuid.uuid4())
        closed_at = START_MS + (i // 2) * 60_000  # pairs share a closing time
        ClosedTrade.create(id=trade_id, session_id=owner, strategy_name='Demo', symbol='ETH-USDT', exchange=BYBIT, type=kind,
                           timeframe='5m', opened_at=closed_at - 30_000, closed_at=closed_at, leverage=rng.choice((1, 2, 5)),
                           created_at=closed_at, updated_at=closed_at, session_mode='livetrade')
        entry_side, exit_side = ('buy', 'sell') if kind == 'long' else ('sell', 'buy')
        legs = rng.randint(2, 5)
        total = 0.0
        for leg in range(legs):
            qty = round(rng.uniform(0.1, 2.0), 4)
            total += qty
            _order(sessions[(i + leg) % 3], closed_at - 30_000 + leg, trade_id=trade_id, side=entry_side,
                   qty=qty if kind == 'long' else -qty, price=round(rng.uniform(90, 110), 3),
                   executed_at=closed_at - 30_000 + leg, fee=rng.choice((None, 0.01, 0.02)))
        remaining = total
        for leg in range(rng.randint(1, 4)):
            qty = remaining if leg == 3 else round(remaining * rng.uniform(0.3, 1.0), 4)
            remaining = round(remaining - qty, 10)
            _order(owner, closed_at - 1_000 + leg, trade_id=trade_id, side=exit_side, qty=-qty if kind == 'long' else qty,
                   price=round(rng.uniform(90, 110), 3), executed_at=closed_at - 1_000 + leg, fee=0.015)
        trade_ids.append(trade_id)

    job = _run(api, 'print("ok")\n', [{'dataset': 'live_trades', 'name': 'trades', 'start': START, 'end': END}])['job']
    assert job['inputs'][0]['count'] == 30
    assert _wait(api, job['id'])['job']['status'] == 'succeeded'
    snapshot = json.loads((project / 'storage' / 'mcp' / 'analysis' / job['id'] / 'inputs' / 'trades.json').read_text())
    records = {record['id']: record for record in snapshot['trades']}
    assert set(records) == set(trade_ids) and len(snapshot['trades']) == 30
    for trade_id in trade_ids:
        _assert_dashboard_values(records[trade_id], _dashboard_trade(api, trade_id))
    _no_fakes(json.dumps(snapshot))


# ---------------------------------------------------------------------------
# Round 2 review: redaction before cuts, session state shapes, one database view per page and
# snapshot input, released transactions, bounded order loading, full-response page bounds
# ---------------------------------------------------------------------------

def _independent_write(db, sql: str, params: tuple = (), timeout: float = 0.5) -> None:
    """Commit a write through a separate SQLite connection, as a live session process would."""
    connection = sqlite3.connect(db.database, timeout=timeout)
    try:
        connection.execute(sql, params)
        connection.commit()
    finally:
        connection.close()


def _in_thread(function) -> None:
    """Run `function` on another thread (another connection), re-raising its failure here."""
    failures = []

    def run():
        try:
            function()
        except Exception as exc:  # re-raised below in the test thread
            failures.append(exc)

    worker = threading.Thread(target=run)
    worker.start()
    worker.join(10)
    assert not worker.is_alive()
    if failures:
        raise failures[0]


def _secret_fragments(text: str) -> list:
    """Any 8-character piece of any fake secret: a partly returned value is a leak too."""
    return [fake[i:i + 8] for fake in ALL_FAKES for i in range(len(fake) - 7) if fake[i:i + 8] in text]


def test_titles_are_redacted_before_they_are_cut(api):
    # The saved secret crosses the 200-character display cut.
    session = _session(key=KEY_A, title='x' * 190 + FAKE_SECRET_A)
    _order(session, START_MS, status='ACTIVE')
    page = _orders(api, start=START, end=END)
    title = page['sessions'][session]['title']
    assert title == 'x' * 190 + '[redacted]' and _secret_fragments(json.dumps(page)) == []


def test_per_session_texts_are_redacted_before_they_are_cut(api):
    cut = session_results.MAX_TEXT_CHARS
    session = _session(key=KEY_A, title=f'run {FAKE_KEY_A}', status='stopped')
    # Cut before redaction, each value would cross its cut with 12 characters on the returned side
    # (enough to be recognized); the texts stay longer than the cuts after redaction too.
    LiveSession.update(description='d' * (cut - 12) + FAKE_SECRET_A + 'e' * 100,
                       exception='boom', traceback='x' * 100 + FAKE_PASSPHRASE_A + 't' * (cut - 12)).where(
        LiveSession.id == session).execute()
    Log.create(id=str(uuid.uuid4()), session_id=session, timestamp=START_MS, type=1,
               message='l' * (session_results.MAX_LOG_LINE_CHARS - 12) + FAKE_SECRET_A + 'm' * 50)
    summary = api.post('/session-results/get', headers=HEADERS, json={'session_type': 'live', 'session_id': session}).json()
    logs = api.post('/session-results/get', headers=HEADERS,
                    json={'session_type': 'live', 'session_id': session, 'section': 'logs'}).json()
    listing = api.post('/session-results/live-sessions', headers=HEADERS, json={}).json()
    assert summary['description_truncated'] and summary['error']['traceback_truncated']
    assert '[redacted]' in summary['description'] and '[redacted]' in summary['error']['traceback_tail']
    assert logs['items'][0]['message'].endswith('[line cut]') and '[redacted]' in logs['items'][0]['message']
    assert listing['sessions'][0]['title'] == 'run [redacted]'
    assert _secret_fragments(json.dumps([summary, logs, listing])) == []


# Stable case names keep collection identical across workers despite random key IDs.
@pytest.mark.parametrize('state', [
    json.dumps({'form': [KEY_A]}),                                     # a form that is not an object
    json.dumps([{'form': {'exchange_api_key_id': KEY_A}}]),            # a state that is not an object
    json.dumps({'form': {'exchange_api_key_id': {'id': KEY_A}}}),      # a key field that is not text
    json.dumps({'form': {'notification_api_key_id': 12}}),
    '{not json',
], ids=['non-object-form', 'non-object-state', 'non-text-exchange-key',
        'non-text-notification-key', 'invalid-json'])
def test_session_states_of_an_unexpected_shape_fail_closed(api, project, state):
    session = _session(state=state)
    _order(session, START_MS, status='ACTIVE', exchange_id=FAKE_SECRET_A)
    _trade(session, START_MS + 1)
    for route in ('live-orders', 'live-trades'):
        response = api.post(f'/session-results/{route}', json={'start': START, 'end': END}, headers=HEADERS)
        assert response.status_code == 500 and response.json()['error_type'] == 'read_failed', response.text
        assert _secret_fragments(response.text) == []
    for dataset in ('live_orders', 'live_trades'):
        body = _run(api, 'print(1)', [{'dataset': dataset, 'start': START, 'end': END}], 500)
        assert body['error_type'] == 'read_failed' and _secret_fragments(json.dumps(body)) == []
        assert _no_workspaces(project)
    body = api.post('/session-results/get', headers=HEADERS,
                    json={'session_type': 'live', 'session_id': session, 'section': 'orders'})
    assert body.status_code == 500 and _secret_fragments(body.text) == []


@pytest.mark.parametrize('state', [None, '', 'null', json.dumps({'other': 1}), json.dumps({'form': None})])
def test_sessions_without_a_readable_form_are_redacted_with_every_saved_key(api, project, state):
    session = _session(state=state if state is not None else 'placeholder')
    if state is None:
        LiveSession.update(state=None).where(LiveSession.id == session).execute()
    _order(session, START_MS, status='ACTIVE', exchange_id=f'{FAKE_SECRET_B}|{FAKE_BOT_TOKEN}')
    page = _orders(api, start=START, end=END)
    assert page['items'][0]['exchange_id'] == '[redacted]|[redacted]' and page['sessions'][session]['exists'] is True
    job = _run(api, 'print(1)', [{'dataset': 'live_orders', 'name': 'o', 'start': START, 'end': END}])['job']
    assert _wait(api, job['id'])['job']['status'] == 'succeeded'
    snapshot = (project / 'storage' / 'mcp' / 'analysis' / job['id'] / 'inputs' / 'o.json').read_text()
    assert '[redacted]|[redacted]' in snapshot and _secret_fragments(snapshot) == []


def test_a_snapshot_input_reads_one_database_view_while_sessions_write(api, db, monkeypatch):
    """Parent probe: counts, rows, and statuses of one input agree although a writer commits mid-stream."""
    db.execute_sql('PRAGMA journal_mode=WAL')
    session = _session()
    ids = [_order(session, START_MS + i, status='ACTIVE') for i in range(4)]
    monkeypatch.setattr(live_history, 'BATCH_SIZE', 2)
    query = live_history.parse_query('live_orders', {'start': START, 'end': END})
    chunks = live_history.iter_dataset_json(query, {})
    output = [next(chunks), next(chunks)]
    # A session cancels the two orders not streamed yet and records a new one.
    _in_thread(lambda: _independent_write(
        db, 'UPDATE "order" SET status = ? WHERE id IN (?, ?)', ('CANCELED', uuid.UUID(ids[2]).hex, uuid.UUID(ids[3]).hex)))
    _in_thread(lambda: _order(session, START_MS + 10, status='ACTIVE'))
    output.extend(chunks)
    snapshot = json.loads(''.join(output))
    assert snapshot['counts_by_status'] == {'ACTIVE': 4} and snapshot['count'] == 4
    assert [row['status'] for row in snapshot['orders']] == ['ACTIVE'] * 4
    assert not db.in_transaction()
    # Afterwards the writes are visible: two cancelled, two untouched, one new.
    assert live_history.list_orders(start=START, end=END)['counts_by_status'] == {'ACTIVE': 3, 'CANCELED': 2}


def test_a_page_reads_one_database_view_while_sessions_write(api, db, monkeypatch):
    db.execute_sql('PRAGMA journal_mode=WAL')
    session = _session()
    first = _trade(session, START_MS + 1000, entry=100.0, exit=110.0, qty=2.0)
    _trade(session, START_MS + 2000)
    real_chunks = live_history._hydration_chunks

    def chunks_after_writes(trades):
        # Between reading the trades and loading their orders, a session adds an executed exit to
        # the first trade, closes a new trade, and opens another.
        _in_thread(lambda: _order(session, START_MS + 1500, trade_id=first, side='sell', qty=-1.0, price=200.0,
                                  executed_at=START_MS + 1500, fee=0.1))
        _in_thread(lambda: _trade(session, START_MS + 3000))
        _in_thread(lambda: _trade(session, None, opened_at=START_MS + 4000))
        return real_chunks(trades)

    monkeypatch.setattr(live_history, '_hydration_chunks', chunks_after_writes)
    page = _trades(api, start=START, end=END)
    assert (page['total'], page['returned'], page['open_trades_not_included']) == (2, 2, 0)
    item = next(item for item in page['items'] if item['id'] == first)
    assert (item['executed_orders'], item['exit_price'], item['qty']) == (2, 110.0, 2.0)


def test_transactions_end_when_a_snapshot_stops_early(api, db, project, monkeypatch):
    """Rollback-journal mode: an open read transaction would hold every writer back."""
    session = _session()
    for i in range(6):
        _order(session, START_MS + i, status='ACTIVE')
    monkeypatch.setattr(live_history, 'BATCH_SIZE', 2)
    query = live_history.parse_query('live_orders', {'start': START, 'end': END})

    chunks = live_history.iter_dataset_json(query, {})
    next(chunks)
    next(chunks)
    assert db.in_transaction()
    with pytest.raises(sqlite3.OperationalError):
        _independent_write(db, 'UPDATE "order" SET fee = 1', timeout=0.1)  # held back while it reads
    chunks.close()
    assert not db.in_transaction()
    _independent_write(db, 'UPDATE "order" SET fee = 1')

    # The byte cap stops writing mid-stream: the transaction ends and nothing is left on disk.
    monkeypatch.setattr(analysis_jobs, 'MAX_INPUT_BYTES', 900)
    workspace = project / 'workspace'
    (workspace / 'inputs').mkdir(parents=True)
    fd = os.open(workspace, os.O_RDONLY)
    try:
        with pytest.raises(ProjectFileError) as refused:
            analysis_jobs._write_inputs(fd, [{'dataset': 'live_orders', 'query': query, 'name': 'orders'}])
        assert refused.value.error_type == 'too_large'
        assert not db.in_transaction()  # checked while the exception (and its traceback) is still alive
    finally:
        os.close(fd)
    assert list((workspace / 'inputs').iterdir()) == []
    _independent_write(db, 'UPDATE "order" SET fee = 2')

    # The same through the route, whose threads keep their connections: writers are not held back.
    assert _run(api, 'print(1)', [{'dataset': 'live_orders', 'start': START, 'end': END}], 413)['error_type'] == 'too_large'
    _independent_write(db, 'UPDATE "order" SET fee = 3')
    _orders(api, start=START, end=END)
    _independent_write(db, 'UPDATE "order" SET fee = 4')
    assert _no_workspaces(project)


def _trade_with_orders(session: str, closed_at: int, entries: int) -> str:
    """A long trade with `entries` executed entry orders and one executed exit."""
    trade_id = str(uuid.uuid4())
    ClosedTrade.create(id=trade_id, session_id=session, strategy_name='Demo', symbol='BTC-USDT', exchange=BYBIT, type='long',
                       timeframe='1h', opened_at=closed_at - 10_000, closed_at=closed_at, leverage=1,
                       created_at=closed_at, updated_at=closed_at, session_mode='livetrade')
    for leg in range(entries):
        _order(session, closed_at - 10_000 + leg, trade_id=trade_id, side='buy', qty=1.0, price=100.0 + leg,
               executed_at=closed_at - 10_000 + leg, fee=0.01)
    _order(session, closed_at, trade_id=trade_id, side='sell', qty=-float(entries), price=120.0, executed_at=closed_at,
           fee=0.01)
    return trade_id


def test_trade_pages_bound_the_orders_they_load(api, monkeypatch):
    session = _session()
    ids = [_trade_with_orders(session, START_MS + 1000 * (i + 1), 1) for i in range(5)]  # 2 executed orders each
    monkeypatch.setattr(live_history, 'MAX_HYDRATED_ORDERS', 4)
    pages = _all_pages(api, 'live-trades', start=START, end=END, order='oldest_first')
    assert [len(page['items']) for page in pages] == [2, 2, 1]
    assert [page['truncated_by_orders'] for page in pages] == [True, True, False]
    assert [tid for page in pages for tid in _ids(page)] == ids
    for page in pages:
        for item in page['items']:
            _assert_dashboard_values(item, _dashboard_trade(api, item['id']))


def test_a_trade_with_too_many_orders_is_refused_not_computed_in_part(api, project, monkeypatch):
    session = _session()
    before = _trade_with_orders(session, START_MS + 1000, 1)
    heavy = _trade_with_orders(session, START_MS + 2000, 4)  # 5 executed orders
    after = _trade_with_orders(session, START_MS + 3000, 1)
    monkeypatch.setattr(live_history, 'MAX_ORDERS_PER_TRADE', 4)
    # Pages return everything before it, then refuse it explicitly.
    first = _trades(api, start=START, end=END, order='oldest_first')
    assert _ids(first) == [before] and first['has_more'] is True and first['truncated_by_orders'] is True
    refused = _trades(api, 413, **first['next_page'])
    assert refused['error_type'] == 'too_many_orders' and heavy in refused['message'] and 'has 5 executed' in refused['message']
    newest = _trades(api, start=START, end=END)
    assert _ids(newest) == [after] and _trades(api, 413, **newest['next_page'])['error_type'] == 'too_many_orders'
    # A page that starts with it is refused at once.
    assert _trades(api, 413, start='2026-09-21T00:00:01.500Z', end=END, order='oldest_first')['error_type'] == 'too_many_orders'
    # A snapshot is refused as a whole, before running anything.
    body = _run(api, 'print(1)', [{'dataset': 'live_trades', 'start': START, 'end': END}], 413)
    assert body['error_type'] == 'too_many_orders' and _no_workspaces(project)
    # Orders themselves need no trade values, so the order history still reads (the three exits
    # fall inside the window; the entries were created 10 seconds before it).
    assert _orders(api, start=START, end=END)['total'] == 3


def test_snapshots_load_orders_in_bounded_chunks_with_exact_values(api, project, monkeypatch):
    session = _session()
    ids = [_trade_with_orders(session, START_MS + 1000 * (i + 1), 1 + i % 3) for i in range(9)]
    monkeypatch.setattr(live_history, 'MAX_HYDRATED_ORDERS', 5)
    loaded = []
    real_executed = live_history._executed_orders

    def recording(trade_ids):
        grouped = real_executed(trade_ids)
        loaded.append(sum(len(orders) for orders in grouped.values()))
        return grouped

    monkeypatch.setattr(live_history, '_executed_orders', recording)
    job = _run(api, 'print(1)', [{'dataset': 'live_trades', 'name': 't', 'start': START, 'end': END}])['job']
    assert job['inputs'][0]['count'] == 9 and max(loaded) <= 5 and len(loaded) > 2
    assert _wait(api, job['id'])['job']['status'] == 'succeeded'
    snapshot = json.loads((project / 'storage' / 'mcp' / 'analysis' / job['id'] / 'inputs' / 't.json').read_text())
    assert [record['id'] for record in snapshot['trades']] == ids
    for record in snapshot['trades']:
        _assert_dashboard_values(record, _dashboard_trade(api, record['id']))


UNICODE_TITLE = ('Ω≈ç√ 中文 🚀 \u0000\u001f "quoted" \\ ' * 20)[:255]


def test_whole_pages_with_many_sessions_and_unicode_fit_the_budget(api, tools, monkeypatch):
    sessions = [_session(title=UNICODE_TITLE) for _ in range(40)]
    ids = [_trade(session, START_MS + i) for i, session in enumerate(sessions)]
    budget = 24 * 1024
    monkeypatch.setattr(live_history, 'MAX_RESPONSE_BYTES', budget)
    pages = _all_pages(api, 'live-trades', start=START, end=END, limit=500, order='oldest_first')
    assert len(pages) > 2 and [tid for page in pages for tid in _ids(page)] == ids
    for page in pages:
        assert live_history._wire_bytes(page) <= budget - live_history.TRANSPORT_ALLOWANCE
        assert len(page['sessions']) == page['returned']
        assert page['sessions'][page['items'][0]['session_id']]['title'] == UNICODE_TITLE[:live_history.MAX_SESSION_TITLE_CHARS]
    # What the real FastMCP server sends, as a JSON string on the wire, stays within the budget.
    server = mcp_server.create_mcp_server(0)
    result = asyncio.run(server.call_tool('get_live_trades', {'start': START, 'end': END, 'limit': 500}))
    contents = result[0] if isinstance(result, tuple) else result
    assert len(json.dumps(contents[0].text, ensure_ascii=False).encode('utf-8')) <= budget
    assert json.loads(contents[0].text)['truncated_by_size'] is True


def test_a_record_that_cannot_fit_a_page_is_refused_explicitly(api, monkeypatch):
    session = _session(title=UNICODE_TITLE)
    _trade(session, START_MS)
    monkeypatch.setattr(live_history, 'MAX_RESPONSE_BYTES', live_history.TRANSPORT_ALLOWANCE + 2048)
    body = _trades(api, 413, start=START, end=END)
    assert body['error_type'] == 'item_too_large' and 'run_analysis' in body['message']


# ---------------------------------------------------------------------------
# Round 2 follow-up: raw scalar arguments, raw session state, read-only per-session snapshots
# ---------------------------------------------------------------------------

def _mcp_call(server, name: str, arguments: dict) -> dict:
    result = asyncio.run(server.call_tool(name, arguments))
    contents = result[0] if isinstance(result, tuple) else result
    return json.loads(contents[0].text)


def test_string_arguments_reach_the_history_tools_exactly_as_sent(api, tools):
    """The text "null" (and other JSON-looking text) is a value, never an omitted filter (FastMCP 1.28.1 decodes it)."""
    session = _session()
    trade = _trade(session, NOW - DAY)
    server = mcp_server.create_mcp_server(0)
    base = {'recent_days': 3}
    # Omitted and a real null mean "no filter"; the text "null" is a filter value like any other.
    assert _ids(_mcp_call(server, 'get_live_trades', base)) == [trade]
    assert _ids(_mcp_call(server, 'get_live_trades', {**base, 'symbol': None})) == [trade]
    as_text = _mcp_call(server, 'get_live_trades', {**base, 'symbol': 'null'})
    assert (as_text['total'], as_text['filters']['symbol']) == (0, 'null')
    assert _mcp_call(server, 'get_live_trades', {**base, 'exchange': '["Bybit USDT Perpetual"]'})['total'] == 0
    assert _mcp_call(server, 'get_live_orders', {**base, 'symbol': 'null'})['total'] == 0
    # Text that FastMCP would have decoded into something else is refused as the text it is.
    for arguments in ({'start': 'null'}, {'end': 'null', 'start': START}, {'session_id': 'null'},
                      {'cursor': 'null', 'start': START, 'end': END}, {'recent_days': 'null'},
                      {'recent_days': '3'}, {'recent_days': 'true'}, {'limit': '5'}, {'limit': 'false'},
                      {'mode': 'null'}, {'mode': 'true'}, {'order': '["newest_first"]'},
                      {'symbol': '{"a": 1}', 'start': 'null'}):
        body = _mcp_call(server, 'get_live_trades', arguments)
        assert body['status'] == 'error' and body['error_type'] in ('invalid_request', 'invalid_cursor'), arguments
    for arguments in ({'time_field': 'null'}, {'status': 'null'}, {'status': '["EXECUTED"]'}):
        assert _mcp_call(server, 'get_live_orders', arguments)['error_type'] == 'invalid_request', arguments
    # Other tools keep FastMCP's documented JSON decoding.
    other = server._tool_manager.get_tool('run_analysis').fn_metadata
    assert other.pre_parse_json({'inputs': '[]'}) == {'inputs': []}


@pytest.mark.parametrize('state', [
    # Parsed as-is these are invalid key fields; JSON cleaning (NaN/inf -> null) would turn them
    # into "no key", so redaction must read the raw column.
    '{"form": {"exchange_api_key_id": NaN}}',
    '{"form": {"exchange_api_key_id": Infinity}}',
    'NaN',
])
def test_redaction_reads_the_raw_state_column_not_a_cleaned_view(api, project, state):
    session = _session(key=KEY_A, state=state)
    _order(session, START_MS, status='ACTIVE', exchange_id=f'x-{FAKE_SECRET_A}')
    responses = [
        api.post('/session-results/get', headers=HEADERS,
                 json={'session_type': 'live', 'session_id': session, 'section': 'orders'}),
        api.post('/session-results/get', headers=HEADERS, json={'session_type': 'live', 'session_id': session}),
        api.post('/session-results/live-sessions', headers=HEADERS, json={}),
        api.post('/session-results/live-orders', headers=HEADERS, json={'start': START, 'end': END}),
    ]
    for response in responses:
        assert response.status_code == 500 and response.json()['error_type'] == 'read_failed', response.text
        assert _secret_fragments(response.text) == []
    body = _run(api, 'print(1)', _live_input(session), 500)
    assert body['error_type'] == 'read_failed' and _no_workspaces(project)


def test_a_live_session_snapshot_reads_one_view_and_writes_nothing(api, db, project, monkeypatch, workers):
    db.execute_sql('PRAGMA journal_mode=WAL')
    # Recorded as running, but no worker: the snapshot reports it stopped without writing that.
    session = _session(key=KEY_A, status='running')
    first = _trade(session, START_MS + 1000)
    _trade(session, START_MS + 2000)
    _equity(session, 3)
    real_orders = session_results._live_orders

    def orders_after_writes(session_id, offset, limit):
        # Between reading the summary and trades and reading the orders, the session keeps trading.
        _in_thread(lambda: _independent_write(db, 'UPDATE "order" SET status = ? WHERE trade_id = ?',
                                              ('CANCELED', uuid.UUID(first).hex)))
        _in_thread(lambda: _trade(session, START_MS + 3000))
        _in_thread(lambda: LiveEquitySnapshot.create(session_id=session, timestamp=START_MS + 999_000, currency='USDT',
                                                     equity=1.0))
        return real_orders(session_id, offset, limit)

    monkeypatch.setattr(session_results, '_live_orders', orders_after_writes)
    code = ('import json\nd = json.load(open("inputs/live.json"))\nc = d["summary"]["counts"]\n'
            'print("view", d["summary"]["session_status"], c["trades"], len(d["closed_trades"]), c["orders"], '
            'len(d["orders"]), c["equity_points"], len(d["equity_curve"]), sorted({o["status"] for o in d["orders"]}))\n')
    job = _run(api, code, _live_input(session))['job']
    finished = _wait(api, job['id'])
    assert "view stopped 2 2 4 4 3 3 ['EXECUTED']" in finished['output'], finished['output']
    row = LiveSession.get(LiveSession.id == session)
    assert (row.status, row.finished_at) == ('running', None)  # nothing was written back
    assert not db.in_transaction()
    _independent_write(db, 'UPDATE "order" SET fee = 9')  # no transaction left holding writers
    # Reading the session the dashboard way still reconciles and writes, exactly as before.
    api.post('/session-results/get', headers=HEADERS, json={'session_type': 'live', 'session_id': session})
    assert LiveSession.get(LiveSession.id == session).status == 'stopped'


# ---------------------------------------------------------------------------
# Round 3: the documented "analyze my trades" workflow, executed as documented
# ---------------------------------------------------------------------------

def _documented_workflow_code() -> str:
    """The Python example of the workflow in jesse://session_analysis, exactly as served."""
    mcp = FakeMCP()
    register_resources(mcp)
    guide = mcp.resources['jesse://session_analysis']()
    workflow = guide[guide.index('### Workflow: "analyze my trades of the last 7 days"'):]
    return workflow.split('```python\n', 1)[1].split('\n```', 1)[0] + '\n'


def _documented_input(discovery: dict, dataset: str = 'live_trades', name: str = 'trades') -> dict:
    """The analysis input the workflow says to build from a discovery response."""
    return {'dataset': dataset, 'name': name, 'start': discovery['range']['start'], 'end': discovery['range']['end'],
            **{key: value for key, value in discovery['filters'].items() if key != 'session_modes' and value is not None}}


def _groups(output: str) -> dict:
    """The workflow's printed groups: header line -> the indented lines under it."""
    groups: dict = {}
    current = None
    for line in output.splitlines():
        if line.startswith('group '):
            current = line
            groups[current] = []
        elif line.startswith('  ') and current:
            groups[current].append(line.strip())
    return groups


def _expected_group(items: list) -> list:
    pnls = [item['pnl'] for item in sorted(items, key=lambda i: (i['closed_at'], i['id']))]
    quote = items[0]['symbol'].split('-')[1]
    mode = items[0]['session_mode']
    return [f'net_closed_trade_pnl={math.fsum(pnls)!r} {quote} wins={sum(1 for p in pnls if p > 0)}/{len(pnls)}',
            f'chart output/cumulative_pnl_{mode}_{quote}.png']


def _seed_workflow_trades(live: str, paper: str) -> dict:
    """Closed trades in several quote currencies, live and paper, one without pnl, one unknown symbol."""
    ids = {
        'usdt': [_trade(live, START_MS + 1000, symbol='BTC-USDT', entry=100.0, exit=110.0, qty=2.0),
                 _trade(live, START_MS + 2000, symbol='BTC-USDT', entry=120.0, exit=115.0, qty=1.0),
                 _trade(live, START_MS + 3000, symbol='SOL-USDT', entry=20.0, exit=21.5, qty=4.0, fees=(0.1, None))],
        'btc': [_trade(live, START_MS + 4000, symbol='ETH-BTC', entry=0.05, exit=0.0512345, qty=0.3, fees=(0.000001, 0.000002)),
                _trade(live, START_MS + 5000, symbol='ETH-BTC', entry=0.051, exit=0.0515, qty=0.2, fees=(0.0000005, 0.0000005))],
        'usd': [_trade(live, START_MS + 6000, symbol='AAPL-USD', entry=200.0, exit=205.0, qty=3.0),
                _trade(live, START_MS + 7000, symbol='AAPL-USD', entry=201.0, exit=199.0, qty=1.0)],
        'unknown': [_trade(live, START_MS + 8000, symbol='WEIRD', entry=10.0, exit=12.0, qty=1.0)],
        'paper': [_trade(paper, START_MS + 9000, symbol='BTC-USDT', entry=100.0, exit=90.0, qty=1.0, mode='papertrade'),
                  _trade(paper, START_MS + 9500, symbol='BTC-USDT', entry=90.0, exit=99.0, qty=1.0, mode='papertrade')],
    }
    # The second AAPL trade lost its exit leg: Jesse cannot compute its pnl (null).
    Order.delete().where((Order.trade_id == ids['usd'][1]) & (Order.side == 'sell')).execute()
    return ids


def test_the_documented_workflow_groups_by_mode_and_quote_and_refuses_unknowns(api, tools, project):
    live, paper = _session(key=KEY_A), _session(mode='papertrade')
    ids = _seed_workflow_trades(live, paper)
    discovery = tools['get_live_trades'](start=START, end=END, mode='all', limit=500)
    assert discovery['all_records_returned'] is True and discovery['total'] == 10
    items = {item['id']: item for item in discovery['items']}
    assert items[ids['usd'][1]]['pnl'] is None

    started = tools['run_analysis'](_documented_workflow_code(), [_documented_input(discovery)])
    manifest = started['job']['inputs'][0]
    assert (manifest['count'], manifest['range'], manifest['filters']) == (10, discovery['range'], discovery['filters'])
    finished = _wait(api, started['job']['id'])
    assert finished['job']['status'] == 'succeeded', finished['output']
    groups = _groups(finished['output'])
    expected = {
        'group mode=livetrade quote=unknown trades=1 unknown_pnl=0 missing_fee_trades=0':
            ['not computed: the symbol is not BASE-QUOTE, so the pnl currency is unknown'],
        'group mode=livetrade quote=BTC trades=2 unknown_pnl=0 missing_fee_trades=0':
            _expected_group([items[i] for i in ids['btc']]),
        'group mode=livetrade quote=USD trades=2 unknown_pnl=1 missing_fee_trades=0':
            ['not computed: 1 of 2 trades have no pnl'],
        'group mode=livetrade quote=USDT trades=3 unknown_pnl=0 missing_fee_trades=1':
            _expected_group([items[i] for i in ids['usdt']]),
        'group mode=papertrade quote=USDT trades=2 unknown_pnl=0 missing_fee_trades=0':
            _expected_group([items[i] for i in ids['paper']]),
    }
    assert groups == expected
    # BTC amounts are printed at full precision (not rounded to cents).
    btc_line = expected['group mode=livetrade quote=BTC trades=2 unknown_pnl=0 missing_fee_trades=0'][0]
    assert abs(float(btc_line.split('=')[1].split()[0]) - (0.3 * 0.0012345 - 0.000003 + 0.2 * 0.0005 - 0.000001)) < 1e-15
    assert 'range 2026-09-21T00:00:00.000Z -> 2026-09-22T00:00:00.000Z | trades 10 | open trades not included 0' in finished['output']

    # One valid chart per computed group, returned to the client as MCP image content.
    charts = sorted(a['path'] for a in finished['artifacts'])
    assert charts == ['cumulative_pnl_livetrade_BTC.png', 'cumulative_pnl_livetrade_USDT.png',
                      'cumulative_pnl_papertrade_USDT.png']
    server = mcp_server.create_mcp_server(0)
    for chart in charts:
        result = asyncio.run(server.call_tool('get_analysis_artifact', {'job_id': started['job']['id'], 'path': chart}))
        assert isinstance(result, CallToolResult) and not result.isError
        image = result.content[1]
        assert isinstance(image, ImageContent) and image.mimeType == 'image/png'
        assert base64.b64decode(image.data).startswith(b'\x89PNG')


def test_the_documented_input_keeps_every_returned_filter(api, tools, project):
    live, paper = _session(key=KEY_A), _session(mode='papertrade')
    ids = _seed_workflow_trades(live, paper)
    code = _documented_workflow_code()
    for arguments, expected_ids in (
        ({}, None),                                                        # default: live only
        ({'symbol': 'BTC-USDT', 'session_id': live}, ids['usdt'][:2]),
        ({'mode': 'paper'}, ids['paper']),
    ):
        discovery = tools['get_live_trades'](start=START, end=END, limit=500, **arguments)
        request = _documented_input(discovery)
        assert 'session_modes' not in request and 'cursor' not in request and 'limit' not in request
        job = tools['run_analysis'](code, [request])['job']
        assert job['inputs'][0]['filters'] == discovery['filters'] and job['inputs'][0]['count'] == discovery['total']
        output = _wait(api, job['id'])['output']
        headers = [line for line in output.splitlines() if line.startswith('group ')]
        if expected_ids is not None:
            assert discovery['total'] == len(expected_ids)
        modes = {line.split()[1] for line in headers}
        assert modes == ({'mode=papertrade'} if arguments.get('mode') == 'paper' else {'mode=livetrade'}), arguments
    # Orders: time_field and status are part of the returned filters and carried the same way.
    orders = tools['get_live_orders'](start=START, end=END, time_field='executed_at', status='EXECUTED')
    request = _documented_input(orders, dataset='live_orders', name='orders')
    assert (request['time_field'], request['status']) == ('executed_at', 'EXECUTED')
    job = tools['run_analysis']('print(1)\n', [request])['job']
    assert job['inputs'][0]['filters'] == orders['filters'] and job['inputs'][0]['count'] == orders['total']


def test_the_documented_code_handles_an_empty_selection(api, tools):
    discovery = tools['get_live_trades'](recent_days=3)
    assert discovery['total'] == 0  # the workflow stops here and runs no analysis
    # The code itself is still valid on an empty snapshot: no groups, no charts.
    job = tools['run_analysis'](_documented_workflow_code(), [_documented_input(discovery)])['job']
    finished = _wait(api, job['id'])
    assert finished['job']['status'] == 'succeeded', finished['output']
    assert 'no closed trades in this window' in finished['output'] and finished['artifacts'] == []
