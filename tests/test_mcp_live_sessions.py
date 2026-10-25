"""
MCP live/paper session management against Jesse's real routes.

The real live, tabs, exchange-key, notification-key, config, and system routers are served
over loopback HTTP by uvicorn from a disposable project with a throwaway SQLite database, and
the MCP live services call them exactly as in production. Three boundaries are replaced, each
by a stand-in that records what reached it:

- the process manager: /live hands the session to `_Processes`, which records the start and
  marks the session active (what the Redis worker set does) but never runs it, and
  `jesse_live.live_mode` is a module whose `run` fails the test if anything calls it;
- jesse.trade: a local HTTP double records unexpected plan preflight requests; MCP starts
  must leave the actual license checks to the session plugin, just like dashboard starts;
- the repositories' unit-test guard, which would otherwise make them skip the database.

Nothing starts a live or paper session, contacts an exchange or jesse.trade, or reads a real
env, key, or wallet file. Key values below are fake sentinels, checked for in every result.
"""
import json
import logging
import os
import socket
import sys
import threading
import time
import types
import uuid
from datetime import datetime, timezone
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import anyio
import peewee
import pytest
import uvicorn
from fastapi import FastAPI, Request

import jesse.helpers as jh
import jesse.mcp.mcp_config as mcp_config
import jesse.mcp.tools.services.live as live_service
from jesse.controllers import (
    config_controller,
    exchange_controller,
    live_controller,
    notification_controller,
    session_results_controller,
    system_controller,
    tabs_controller,
)
from jesse.info import exchange_info
from jesse.mcp.server import create_mcp_server
from jesse.mcp.tools.services.session_config import live_engine_config
from jesse.models.ExchangeApiKeys import ExchangeApiKeys
from jesse.models.LiveSession import LiveSession
from jesse.models.NotificationApiKeys import NotificationApiKeys
from jesse.models.OpenTab import OpenTab
from jesse.models.Option import Option
from jesse.repositories import live_session_repository, open_tab_repository
from jesse.services import auth, general_info
from jesse.services.multiprocessing import process_manager

PASSWORD = 'live-sessions-test-password'
AUTH = sha256(PASSWORD.encode('utf-8')).hexdigest()
FAKE_LICENSE = 'LIVE-TEST-LICENSE-TOKEN-7373'
FAKE_API_KEY = 'QZXLlive-key-sentinel-0101VWKL'
FAKE_API_SECRET = 'QZXMlive-secret-sentinel-0202VWKM'
FAKE_PASSPHRASE = 'QZXNlive-passphrase-sentinel-VWKN'
FAKE_BOT_TOKEN = 'QZXOlive-telegram-bot-sentinel-VWKO'
SENTINELS = (FAKE_API_KEY, FAKE_API_SECRET, FAKE_PASSPHRASE, FAKE_BOT_TOKEN, FAKE_LICENSE)
SPOT_KEY = '2f6b1b8e-8b1e-4c9e-9a51-0d7c2f7d1a01'
BYBIT_KEY = '2f6b1b8e-8b1e-4c9e-9a51-0d7c2f7d1a02'
TELEGRAM_KEY = '2f6b1b8e-8b1e-4c9e-9a51-0d7c2f7d1a03'
WAIT_SECONDS = 15

LIVE_LOGGING = {
    'order_submission': True, 'order_cancellation': True, 'order_execution': True, 'position_opened': True,
    'position_increased': True, 'position_reduced': True, 'position_closed': True, 'shorter_period_candles': False,
    'trading_candles': True, 'balance_update': True, 'strategy_execution': True, 'exchange_ws_reconnection': True,
}
NOTIFICATIONS = {
    'enabled': True, 'position_report_timeframe': '1h',
    'events': {
        **{event: True for event in ('errors', 'started_session', 'terminated_session', 'submitted_orders',
                                    'cancelled_orders', 'executed_orders', 'opened_position', 'updated_position',
                                    'exchange_ws_reconnection', 'closed_position')},
        'account_balance': False,
    },
}
# Saved settings as the dashboard stores them: legacy live section plus remembered session defaults.
SETTINGS = {
    'backtest': {'exchanges': {}},
    'optimization': {},
    'live': {
        'persistency': True, 'generate_candles_from_1m': False, 'warm_up_candles': 240,
        'logging': {'balance_update': False}, 'notifications': {'position_report_timeframe': '4h'},
        'exchanges': {'Binance Perpetual Futures': {'fee': 0.0005, 'balance': 5000, 'futures_leverage': 3,
                                                   'futures_leverage_mode': 'isolated', 'type': 'futures'}},
    },
    'session_defaults': {'live': {
        'paper_by_exchange': {'Bybit USDT Perpetual': {
            'persistency': False, 'warm_up_candles': 300,
            'exchange': {'name': 'Bybit USDT Perpetual', 'balance': 777, 'fee': 0.001, 'simulation_model': 'perpetual_futures',
                         'futures_leverage': 7, 'futures_leverage_mode': 'cross', 'annualization': 365}}},
        'live_by_credential': {SPOT_KEY: {
            'persistency': True, 'warm_up_candles': 400,
            'exchange': {'name': 'Binance Spot', 'balance': 1, 'fee': 0.002, 'simulation_model': 'perpetual_futures'}}},
    }},
}
ROUTES = [{'strategy': 'Demo', 'symbol': 'BTC-USDT', 'timeframe': '1h'}]


# ---------------------------------------------------------------------------
# Stand-ins
# ---------------------------------------------------------------------------

class _Processes:
    """Stands in for process_manager: records starts and cancels and keeps the active set."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.active: set = set()
        self.started: list = []
        self.cancelled: list = []
        # Seconds add_task waits, to hold overlapping start requests inside the route (race tests).
        self.start_delay = 0.0
        # How the next add_task fails, as the real one can: 'before' the process starts (the real
        # add_task then removes the active marker again) or 'after' it started (marker kept).
        self.fail_launch = None
        # Set when a start reaches add_task (the route then holds its lifecycle lock), so a race
        # test can send its competing request while the start is inside.
        self.entered = threading.Event()

    def add_task(self, function, *args) -> None:
        self.entered.set()
        time.sleep(self.start_delay)
        with self.lock:
            failure, self.fail_launch = self.fail_launch, None
            if failure == 'before':
                raise OSError('could not start the process')
            self.started.append((function, args))
            self.active.add(args[0])
            if failure == 'after':
                raise KeyError('APP_PORT')

    def cancel_process(self, client_id) -> None:
        with self.lock:
            self.cancelled.append(client_id)
            self.active.discard(client_id)


class _JesseTrade:
    """
    Local HTTP double of jesse.trade's /v2/user-info (the plan and its limits). It answers only
    the fake license token; `status` can make it fail. Records each request's Authorization.
    """

    def __init__(self) -> None:
        self.status = 200
        self.plan = 'pro'
        self.limits = {'live_trading_tabs': 2, 'trading_routes': 5, 'data_routes': 5, 'timeframes': [], 'exchanges': {}}
        self.authorizations: list = []
        double = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                double.authorizations.append((self.path, self.headers.get('Authorization')))
                if self.path != '/api/v2/user-info' or double.status != 200:
                    status, body = (double.status if double.status != 200 else 404), {'message': 'unavailable'}
                elif self.headers.get('Authorization') != f'Bearer {FAKE_LICENSE}':
                    status, body = 401, {'message': 'Invalid license'}
                else:
                    status, body = 200, {'plan': double.plan, 'limits': double.limits}
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *_args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.url = f'http://127.0.0.1:{self.server.server_address[1]}/api'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)


class _Server:
    """Serve an ASGI app with uvicorn on an ephemeral loopback port in a daemon thread."""

    def __init__(self, app) -> None:
        self.socket = socket.socket()
        self.socket.bind(('127.0.0.1', 0))
        self.url = f'http://127.0.0.1:{self.socket.getsockname()[1]}'
        self.server = uvicorn.Server(uvicorn.Config(app, log_level='warning', access_log=False, lifespan='off'))
        self.thread = threading.Thread(target=self.server.run, kwargs={'sockets': [self.socket]}, daemon=True)

    def __enter__(self):
        self.thread.start()
        deadline = time.monotonic() + WAIT_SECONDS
        while not self.server.started:
            assert self.thread.is_alive() and time.monotonic() < deadline, 'test server failed to start'
            time.sleep(0.01)
        return self

    def __exit__(self, *_exc):
        self.server.should_exit = True
        self.thread.join(WAIT_SECONDS)
        self.socket.close()


class _RepositoryHelpers(types.SimpleNamespace):
    """jesse.helpers for the repositories, without their unit-test guard that skips the database."""

    def __getattr__(self, name):
        return getattr(jh, name)

    @staticmethod
    def is_unit_testing() -> bool:
        return False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def processes(monkeypatch) -> _Processes:
    fake = _Processes()
    monkeypatch.setattr(process_manager, 'add_task', fake.add_task)
    monkeypatch.setattr(process_manager, 'cancel_process', fake.cancel_process)
    monkeypatch.setattr(type(process_manager), 'active_workers', property(lambda _self: set(fake.active)))
    live_mode = types.ModuleType('jesse_live.live_mode')

    def run(*_args, **_kwargs):
        raise AssertionError('a live or paper session process was started')

    live_mode.run = run
    try:
        import jesse_live
    except ImportError:
        # The proprietary plugin is absent (open-source CI). The routes under test only import its
        # live_mode module and read jesse_live.version to report the plugin as installed.
        jesse_live = types.ModuleType('jesse_live')
        jesse_live.__path__ = []
        version = types.ModuleType('jesse_live.version')
        version.__version__ = '0.0.0-test'
        monkeypatch.setitem(sys.modules, 'jesse_live', jesse_live)
        monkeypatch.setitem(sys.modules, 'jesse_live.version', version)
    monkeypatch.setitem(sys.modules, 'jesse_live.live_mode', live_mode)
    monkeypatch.setattr(jesse_live, 'live_mode', live_mode, raising=False)
    return fake


@pytest.fixture
def jesse_trade(monkeypatch):
    double = _JesseTrade()
    double.thread.start()
    monkeypatch.setattr(general_info, 'JESSE_API_URL', double.url)
    # Update checks (PyPI) are unrelated to the plan and stay offline.
    monkeypatch.setattr(general_info, '_get_update_info', lambda _bucket: {})
    yield double
    double.server.shutdown()
    double.server.server_close()


@pytest.fixture
def plugin(monkeypatch) -> dict:
    """Whether the live plugin counts as installed (jh.has_live_trade_plugin)."""
    state = {'installed': True}
    monkeypatch.setattr(jh, 'has_live_trade_plugin', lambda: state['installed'])
    return state


@pytest.fixture
def jesse(tmp_path, monkeypatch, processes, jesse_trade, plugin):
    project = tmp_path / 'project'
    for strategy in ('Demo', 'Other'):
        (project / 'strategies' / strategy).mkdir(parents=True)
        (project / 'strategies' / strategy / '__init__.py').write_text(f'class {strategy}:\n    pass\n')
    (project / 'storage').mkdir()
    monkeypatch.chdir(project)
    monkeypatch.setitem(auth.ENV_VALUES, 'PASSWORD', PASSWORD)
    monkeypatch.setitem(auth.ENV_VALUES, 'LICENSE_API_TOKEN', FAKE_LICENSE)
    monkeypatch.setattr(live_session_repository, 'jh', _RepositoryHelpers())
    monkeypatch.setattr(open_tab_repository, 'jh', _RepositoryHelpers())
    # SQLite keeps datetimes as text that peewee cannot parse back when they carry a zone.
    monkeypatch.setattr(jh, 'now_to_datetime', lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    requests_seen: list = []
    app = FastAPI()

    @app.exception_handler(auth.InvalidAuthError)
    async def invalid_auth_handler(_request, _exc):
        return auth.unauthorized_response()

    @app.middleware('http')
    async def record(request: Request, call_next):
        requests_seen.append((request.method, request.url.path))
        return await call_next(request)

    for router in (config_controller.router, exchange_controller.router, notification_controller.router,
                   system_controller.router, tabs_controller.router, live_controller.router,
                   session_results_controller.router):
        app.include_router(router)

    # uvicorn serves routes from several threads; SQLite waits up to 5 s for another thread's write lock
    # instead of failing at once.
    db = peewee.SqliteDatabase(str(tmp_path / 'live.db'), pragmas={'busy_timeout': 5000})
    models = [LiveSession, ExchangeApiKeys, NotificationApiKeys, OpenTab, Option]
    with db.bind_ctx(models):
        db.create_tables(models)
        Option.create(id=str(uuid.uuid4()), updated_at=jh.now(True), type='config', json=json.dumps(SETTINGS))
        created = datetime(2026, 9, 1)
        ExchangeApiKeys.create(id=SPOT_KEY, exchange_name='Binance Spot', name='spot main', api_key=FAKE_API_KEY,
                               api_secret=FAKE_API_SECRET, additional_fields='{}', created_at=created)
        ExchangeApiKeys.create(id=BYBIT_KEY, exchange_name='Bybit USDT Perpetual', name='bybit futures',
                               api_key=FAKE_API_KEY + 'B', api_secret=FAKE_API_SECRET + 'B',
                               additional_fields=json.dumps({'api_passphrase': FAKE_PASSPHRASE}), created_at=created)
        NotificationApiKeys.create(id=TELEGRAM_KEY, name='phone', driver='telegram',
                                   fields=json.dumps({'bot_token': FAKE_BOT_TOKEN, 'chat_id': '9876543210'}),
                                   created_at=created)
        with _Server(app) as server:
            monkeypatch.setattr(mcp_config, 'JESSE_API_URL', server.url)
            monkeypatch.setattr(mcp_config, 'JESSE_PASSWORD', PASSWORD)
            monkeypatch.setattr(mcp_config, 'DASHBOARD_URL', 'https://dash.example')
            yield types.SimpleNamespace(project=project, requests=requests_seen, processes=processes,
                                        jesse_trade=jesse_trade, plugin=plugin, db=db)
    db.close()


def _row(session_id: str) -> LiveSession:
    return LiveSession.get(LiveSession.id == session_id)


def _form(session_id: str) -> dict:
    return json.loads(_row(session_id).state)['form']


def _settings_json() -> str:
    return Option.get(Option.type == 'config').json


def _paper(**overrides) -> dict:
    arguments = {'paper_mode': True, 'exchange': 'Binance Perpetual Futures', 'routes': json.dumps(ROUTES)}
    arguments.update(overrides)
    return live_service.create_live_draft_service(**arguments)


def _no_secrets(*results) -> None:
    text = json.dumps(results)
    for sentinel in SENTINELS:
        assert sentinel not in text
        assert sentinel[:4] + '***' not in text and sentinel[-4:] not in text


def _writes(jesse) -> list:
    return [path for method, path in jesse.requests
            if path in ('/live', '/live/cancel', '/live/update-state') or path.endswith(('/remove', '/notes'))]


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def test_live_tools_are_registered_with_explicit_mode_and_honest_stop_semantics():
    tools = {tool.name: tool for tool in create_mcp_server(0)._tool_manager.list_tools()}
    live_tools = {'create_live_draft', 'update_live_draft', 'copy_live_session', 'start_live_session',
                  'restart_live_session', 'stop_live_session', 'update_live_session_notes', 'delete_live_session'}
    assert live_tools <= set(tools) and all(tools[name].is_async for name in live_tools)
    # No order placement, liquidation, or secret-reading tool exists. get_live_orders only reads
    # the orders Jesse recorded (test_mcp_live_history.py).
    read_only = {'get_live_orders'}
    assert not [name for name in tools
                if name not in read_only and any(word in name for word in ('order', 'liquidat', 'position', 'close_'))]

    create = tools['create_live_draft'].parameters
    # Required arguments are stated in the description and enforced by the service, not by the
    # schema: FastMCP's error for a missing argument would quote every other argument.
    assert create.get('required') is None
    assert '`paper_mode` and `routes` are required' in tools['create_live_draft'].description
    assert create['properties']['paper_mode']['type'] == 'boolean'
    for key_field in ('exchange_api_key_id', 'notification_api_key_id'):
        assert create['properties'][key_field]['anyOf'] == [{'type': 'string'}, {'type': 'null'}]
    assert {'type': 'string'} in create['properties']['routes']['anyOf']
    assert 'REAL funds' in tools['create_live_draft'].description and 'PAPER' in tools['create_live_draft'].description
    stop = tools['stop_live_session'].description
    assert 'does\n        not by itself mean positions are closed' in stop or 'not by itself mean positions are closed' in ' '.join(stop.split())
    assert 'persistency on leaves orders and positions' in ' '.join(stop.split())
    update = tools['update_live_draft']
    assert update.parameters.get('required') is None and '`session_id` is required' in update.description
    assert update.parameters['properties']['session_id']['type'] == 'string'
    for name in live_tools - {'create_live_draft', 'update_live_draft'}:
        assert tools[name].parameters['required'][0] == 'session_id'


def test_stop_semantics_match_the_live_plugin_termination_rule():
    """The stop text states LiveExchange._on_termination's rule, read from the installed plugin."""
    import inspect
    LiveExchange = pytest.importorskip('jesse_live.exchanges.LiveExchange').LiveExchange

    source = inspect.getsource(LiveExchange._on_termination)
    assert "if not jh.get_config('env.data.persistency') or jh.is_paper_trading():" in source
    assert 'self._cancel_pre_existing_orders()' in source and 'self._close_existing_positions()' in source
    text = ' '.join(live_service.STOP_SEMANTICS.split())
    assert 'a paper session, or a live session whose persistency setting is off, cancels the open orders' in text
    assert 'with persistency on leaves its orders and positions on the exchange' in text
    # The stop is noticed by live_mode.run's once-per-second job, which only starts after the
    # startup checks (the license check in init), hence "one still starting once its startup checks finish".
    run_source = inspect.getsource(pytest.importorskip('jesse_live.live_mode').run)
    stop_check = 'if is_process_active(client_id) is False:'
    assert '@tl_0.job(interval=timedelta(seconds=1))' in run_source and stop_check in run_source
    assert run_source.index('init(config)') < run_source.index(stop_check)
    assert 'one still starting once its startup checks' in text


# ---------------------------------------------------------------------------
# Plugin gate and credentials
# ---------------------------------------------------------------------------

def test_every_live_tool_needs_the_live_plugin_and_writes_nothing_without_it(jesse):
    jesse.plugin['installed'] = False
    session_id = str(uuid.uuid4())
    results = [
        _paper(),
        live_service.update_live_draft_service(session_id, debug_mode=False),
        live_service.copy_live_session_service(session_id),
        live_service.start_live_session_service(session_id),
        live_service.stop_live_session_service(session_id),
        live_service.update_live_session_notes_service(session_id, title='x'),
        live_service.delete_live_session_service(session_id),
    ]
    assert [(r['status'], r['error_type']) for r in results] == [('error', 'live_plugin_unavailable')] * 7
    assert _writes(jesse) == [] and LiveSession.select().count() == 0 and jesse.processes.started == []


def test_dashboard_authentication_failures_are_typed_and_leak_nothing(jesse, monkeypatch):
    monkeypatch.setattr(mcp_config, 'JESSE_PASSWORD', 'wrong-password')
    result = _paper()
    assert result['error_type'] == 'authentication_failed' and 'wrong-password' not in json.dumps(result)

    monkeypatch.setattr(mcp_config, 'JESSE_API_URL', 'http://127.0.0.1:9')
    unreachable = live_service.start_live_session_service(str(uuid.uuid4()))
    assert unreachable['error_type'] == 'connection_error'
    assert LiveSession.select().count() == 0


# ---------------------------------------------------------------------------
# Drafts and their own configuration
# ---------------------------------------------------------------------------

def test_a_paper_draft_gets_the_dashboard_default_for_its_exchange_and_shared_settings_stay_unchanged(jesse):
    before = _settings_json()

    result = _paper(title='BTC paper', description='from MCP')

    assert result['status'] == 'success' and result['mode'] == 'paper' and 'no real funds' in result['trading']
    assert result['exchange_api_key'] is None and result['session_status'] == 'draft'
    session_id = result['session_id']
    assert result['dashboard_url'] == f'https://dash.example/#/live/{session_id}'
    expected = {
        'persistency': True, 'generate_candles_from_1m': False,
        'logging': {**LIVE_LOGGING, 'balance_update': False}, 'warm_up_candles': 240,
        'order_backup_check_seconds': 10, 'candle_backup_refresh_seconds': None,
        'notifications': {**NOTIFICATIONS, 'position_report_timeframe': '4h'},
        'exchange': {'name': 'Binance Perpetual Futures', 'type': 'futures', 'simulation_model': 'perpetual_futures',
                     'annualization': 365, 'balance': 5000, 'fee': 0.0005, 'futures_leverage_mode': 'isolated',
                     'futures_leverage': 3},
    }
    assert result['config'] == expected
    row = _row(session_id)
    assert (row.status, row.session_mode, row.exchange, row.title, row.description) == (
        'draft', 'papertrade', 'Binance Perpetual Futures', 'BTC paper', 'from MCP')
    assert _form(session_id) == {
        'debug_mode': True, 'paper_mode': True, 'exchange_api_key_id': '', 'notification_api_key_id': '',
        'exchange': 'Binance Perpetual Futures', 'routes': ROUTES, 'data_routes': [], 'config': expected,
    }
    assert _settings_json() == before and jesse.processes.started == []


def test_remembered_paper_and_credential_profiles_are_used_like_the_dashboard(jesse):
    paper = _paper(exchange='Bybit USDT Perpetual')
    live = live_service.create_live_draft_service(paper_mode=False, exchange_api_key_id=SPOT_KEY, routes=json.dumps(ROUTES),
                                                  notification_api_key_id=TELEGRAM_KEY)
    unmapped = live_service.create_live_draft_service(paper_mode=False, exchange_api_key_id=BYBIT_KEY, routes=json.dumps(ROUTES))

    assert paper['config']['persistency'] is False and paper['config']['warm_up_candles'] == 300
    assert paper['config']['exchange'] == {'name': 'Bybit USDT Perpetual', 'type': 'futures', 'simulation_model': 'perpetual_futures',
                                           'annualization': 365, 'balance': 777, 'fee': 0.001, 'futures_leverage_mode': 'cross',
                                           'futures_leverage': 7}
    # A real session uses its key's profile, with the venue's own market type (Binance Spot is spot).
    assert live['mode'] == 'live' and 'REAL' in live['trading'] and live['exchange'] == 'Binance Spot'
    assert live['exchange_api_key'] == {'id': SPOT_KEY, 'name': 'spot main'}
    assert live['notification_api_key'] == {'id': TELEGRAM_KEY, 'name': 'phone', 'driver': 'telegram'}
    assert live['config']['warm_up_candles'] == 400 and live['config']['persistency'] is True
    assert live['config']['exchange'] == {'name': 'Binance Spot', 'type': 'spot', 'simulation_model': 'spot', 'annualization': 365,
                                          'balance': 1, 'fee': 0.002, 'futures_leverage_mode': 'cross', 'futures_leverage': 5}
    assert _row(live['session_id']).session_mode == 'livetrade'
    assert _form(live['session_id'])['exchange_api_key_id'] == SPOT_KEY
    # A key without a remembered profile falls back to its exchange's profile.
    assert unmapped['exchange'] == 'Bybit USDT Perpetual' and unmapped['config']['exchange']['balance'] == 777
    _no_secrets(paper, live, unmapped)
    stored = ''.join(row.state for row in LiveSession.select())
    assert not any(sentinel in stored for sentinel in SENTINELS)


def test_config_overrides_are_validated_and_stay_in_the_draft(jesse):
    before = _settings_json()
    result = _paper(config=json.dumps({'warm_up_candles': 50, 'persistency': False,
                                       'exchange': {'balance': 1234.5, 'futures_leverage': 2, 'name': 'Ignored'}}))
    assert result['config']['warm_up_candles'] == 50 and result['config']['persistency'] is False
    assert result['config']['exchange']['balance'] == 1234.5 and result['config']['exchange']['futures_leverage'] == 2
    assert result['config']['exchange']['name'] == 'Binance Perpetual Futures'
    assert _settings_json() == before

    for bad in ({'warmup': 1}, {'warm_up_candles': -1}, {'warm_up_candles': True}, {'persistency': 'yes'},
                {'exchange': {'futures_leverage': 0}}, {'exchange': {'futures_leverage_mode': 'hedge'}},
                {'exchange': {'balance': -5}}, {'exchange': {'api_key': 'x'}}, {'logging': []}, [1],
                # Unknown or invalid overrides must be refused rather than replaced by defaults.
                {'logging': {'order_submision': False}}, {'logging': {'order_submission': 'no'}},
                {'notifications': {'events': {'erors': False}}}, {'notifications': {'enabled': 1}},
                {'notifications': {'position_report_timeframe': '7m'}}, {'notifications': {'chat_id': 'x'}},
                {'exchange': {'simulation_model': 'perp'}}, {'exchange': {'type': 'margin'}},
                {'exchange': {'annualization': 300}}, {'exchange': {'annualization': True}},
                {'order_backup_check_seconds': -1}, {'order_backup_check_seconds': None},
                {'order_backup_check_seconds': '30'}, {'candle_backup_refresh_seconds': -1},
                {'candle_backup_refresh_seconds': True}):
        refused = _paper(config=json.dumps(bad))
        assert (refused['status'], refused['error_type']) == ('error', 'invalid_request'), bad
    assert _paper(config='{not json')['error_type'] == 'invalid_request'
    assert LiveSession.select().count() == 1

    # Valid nested overrides are applied to this draft only.
    nested = _paper(exchange='Bybit USDT Perpetual', config={
        'logging': {'balance_update': True, 'trading_candles': False},
        'notifications': {'position_report_timeframe': '4h', 'events': {'executed_orders': False}},
        'exchange': {'simulation_model': 'spot', 'annualization': 252},
    })
    assert nested['status'] == 'success', nested
    assert nested['config']['logging']['trading_candles'] is False and nested['config']['logging']['balance_update'] is True
    assert nested['config']['notifications']['events']['executed_orders'] is False
    assert nested['config']['notifications']['position_report_timeframe'] == '4h'
    assert (nested['config']['exchange']['simulation_model'], nested['config']['exchange']['annualization']) == ('spot', 252)
    assert _settings_json() == before


def test_real_sessions_follow_the_venue_margin_modes(jesse, monkeypatch):
    cross_only = {**exchange_info['Bybit USDT Perpetual'], 'supported_leverage_modes': ['cross']}
    monkeypatch.setitem(exchange_info, 'Bybit USDT Perpetual', cross_only)
    refused = live_service.create_live_draft_service(paper_mode=False, exchange_api_key_id=BYBIT_KEY, routes=json.dumps(ROUTES),
                                                     config=json.dumps({'exchange': {'futures_leverage_mode': 'isolated'}}))
    assert refused['error_type'] == 'invalid_request' and 'cross' in refused['message']
    # Paper sessions simulate both margin modes.
    assert _paper(exchange='Bybit USDT Perpetual', config=json.dumps({'exchange': {'futures_leverage_mode': 'isolated'}}))['status'] == 'success'


def test_mode_exchange_and_key_rules(jesse):
    def error(**arguments):
        result = live_service.create_live_draft_service(routes=json.dumps(ROUTES), **arguments)
        assert result['status'] == 'error', arguments
        return result['error_type']

    assert error(paper_mode=True, exchange='Massive Stocks') == 'unsupported_exchange'
    assert error(paper_mode=True) == 'unsupported_exchange'
    assert error(paper_mode=True, exchange='Binance Spot', exchange_api_key_id=SPOT_KEY) == 'invalid_request'
    assert error(paper_mode=False, exchange='Binance Spot') == 'key_required'
    assert error(paper_mode=False, exchange_api_key_id=str(uuid.uuid4())) == 'key_not_found'
    assert error(paper_mode=False, exchange_api_key_id=SPOT_KEY, exchange='Bybit USDT Perpetual') == 'exchange_mismatch'
    assert error(paper_mode=True, exchange='Binance Spot', notification_api_key_id=str(uuid.uuid4())) == 'notification_key_not_found'
    # The mode must be stated: a missing or ambiguous value is never taken as either mode.
    for unclear in (None, 'yes', 1, 0, '', 'paper'):
        assert error(paper_mode=unclear, exchange='Binance Spot') == 'invalid_request', unclear
    assert live_service.create_live_draft_service(paper_mode=True, exchange='Binance Spot', routes=None)['error_type'] == 'invalid_request'
    # A secret pasted into an ID field by mistake is never reflected back, whatever its type.
    for field in ('exchange_api_key_id', 'notification_api_key_id'):
        for pasted_value in (FAKE_API_SECRET, {'api_key': FAKE_API_KEY, 'api_secret': FAKE_API_SECRET}, [FAKE_API_SECRET]):
            pasted = live_service.create_live_draft_service(paper_mode=False, routes=json.dumps(ROUTES),
                                                            **{'exchange_api_key_id': SPOT_KEY, field: pasted_value})
            assert pasted['status'] == 'error', (field, pasted_value)
            _no_secrets(pasted)
    assert LiveSession.select().count() == 0
    # Clients that send booleans as text still state the mode explicitly.
    assert error(paper_mode='TRUE', exchange='Massive Stocks') == 'unsupported_exchange'
    assert live_service.create_live_draft_service(paper_mode='true', exchange='Binance Spot', routes=ROUTES)['mode'] == 'paper'
    assert live_service.create_live_draft_service(paper_mode='false', exchange_api_key_id=SPOT_KEY, routes=ROUTES)['mode'] == 'live'


@pytest.mark.parametrize('routes, data_routes, message', [
    ([], [], 'At least one trading route is required'),
    ([{'strategy': 'Demo', 'symbol': '', 'timeframe': '1h'}], [], 'You must fill all the parameters'),
    ([{'strategy': 'Demo', 'symbol': 'BTCUSDT', 'timeframe': '1h'}], [], 'must contain "-"'),
    ([{'strategy': 'Demo', 'symbol': 'BTC-USDT', 'timeframe': '1h'}, {'strategy': 'Other', 'symbol': 'BTC-USDT', 'timeframe': '4h'}],
     [], 'can be traded only once'),
    ([{'strategy': 'Demo', 'symbol': 'BTC-USDT', 'timeframe': '1h'}, {'strategy': 'Other', 'symbol': 'ETH-USDC', 'timeframe': '4h'}],
     [], 'same quote asset'),
    (ROUTES, [{'symbol': 'ETH-USDT', 'timeframe': '4h'}, {'symbol': 'ETH-USDT', 'timeframe': '4h'}], 'can be traded only once'),
    (ROUTES, [{'symbol': 'BTC-USDT', 'timeframe': '1h'}], "Data routes' timeframe and trading routes' timeframe must be different"),
    ([{'strategy': 'Demo', 'symbol': 'BTC-USDT', 'timeframe': '7m'}], [], 'Unsupported timeframe'),
    ([{'strategy': 'Missing', 'symbol': 'BTC-USDT', 'timeframe': '1h'}], [], 'Strategy not found'),
    (['BTC-USDT'], [], 'Each route must be an object'),
])
def test_the_dashboard_route_rules_apply(jesse, routes, data_routes, message):
    result = _paper(routes=json.dumps(routes), data_routes=json.dumps(data_routes))
    assert (result['status'], result['error_type']) == ('error', 'invalid_routes')
    assert message in result['message']
    assert LiveSession.select().count() == 0


def test_only_drafts_change_and_updates_revalidate_the_whole_form(jesse):
    draft = _paper()['session_id']

    updated = live_service.update_live_draft_service(
        draft, routes=json.dumps([{'strategy': 'Other', 'symbol': 'ETH-USDT', 'timeframe': '4h'}]),
        data_routes=json.dumps([{'symbol': 'ETH-USDT', 'timeframe': '1D'}]), debug_mode=False,
        config=json.dumps({'exchange': {'balance': 42}}))
    assert updated['status'] == 'success'
    form = _form(draft)
    assert form['routes'] == [{'strategy': 'Other', 'symbol': 'ETH-USDT', 'timeframe': '4h'}]
    assert form['debug_mode'] is False and form['config']['exchange']['balance'] == 42
    # Unchanged settings survive an update; only the override changed.
    assert form['config']['exchange']['futures_leverage'] == 3 and form['config']['warm_up_candles'] == 240

    # Switching to real funds needs a key and takes its exchange; the draft keeps its own config.
    to_live = live_service.update_live_draft_service(draft, paper_mode=False, exchange_api_key_id=BYBIT_KEY)
    assert to_live['mode'] == 'live' and _form(draft)['exchange'] == 'Bybit USDT Perpetual'
    assert _form(draft)['config']['exchange']['name'] == 'Bybit USDT Perpetual'
    assert _row(draft).session_mode == 'papertrade'  # /live/update-state keeps a draft row's mode; /live sets it.
    back = live_service.update_live_draft_service(draft, paper_mode=True, exchange='Binance Spot')
    assert back['mode'] == 'paper' and back['exchange_api_key'] is None
    # Like a dashboard tab, the paper draft remembers the key selection for switching back.
    assert _form(draft)['exchange_api_key_id'] == BYBIT_KEY
    assert live_service.update_live_draft_service(draft, routes='[]')['error_type'] == 'invalid_routes'

    LiveSession.update(status='stopped').where(LiveSession.id == draft).execute()
    refused = live_service.update_live_draft_service(draft, debug_mode=True)
    assert (refused['error_type'], refused['session_status']) == ('not_draft', 'stopped')
    assert live_service.update_live_draft_service(str(uuid.uuid4()), debug_mode=True)['error_type'] == 'not_found'
    assert live_service.update_live_draft_service('not-a-uuid')['error_type'] == 'invalid_request'


def test_notes_update_any_session(jesse):
    draft = _paper()['session_id']
    result = live_service.update_live_session_notes_service(draft, title='Renamed', description='why')
    assert result['status'] == 'success'
    assert result['dashboard_url'] == f'https://dash.example/#/live/{draft}'
    assert (_row(draft).title, _row(draft).description) == ('Renamed', 'why')
    assert live_service.update_live_session_notes_service(draft)['error_type'] == 'invalid_request'
    assert live_service.update_live_session_notes_service(str(uuid.uuid4()), title='x')['error_type'] == 'not_found'


# ---------------------------------------------------------------------------
# Start, stop, restart
# ---------------------------------------------------------------------------

def test_starting_a_paper_draft_sends_the_dashboard_request_and_runs_nothing_itself(jesse):
    draft = _paper(exchange='Bybit USDT Perpetual', notification_api_key_id=TELEGRAM_KEY)
    before = _settings_json()

    result = live_service.start_live_session_service(draft['session_id'])

    assert result['status'] == 'success' and result['mode'] == 'paper' and result['session_status'] == 'starting'
    assert 'plan_check' not in result
    [(function, args)] = jesse.processes.started
    assert function is sys.modules['jesse_live.live_mode'].run  # handed over, never called
    session_id, debug, exchange, key_id, notification_id, config, routes, data_routes, mode = args
    assert (session_id, debug, exchange, key_id, notification_id) == (
        draft['session_id'], True, 'Bybit USDT Perpetual', '', TELEGRAM_KEY)
    assert config == live_engine_config(draft['config'])
    assert config['exchanges'] == {'Bybit USDT Perpetual': draft['config']['exchange']}
    assert (routes, data_routes, mode) == (ROUTES, [], 'papertrade')
    row = _row(draft['session_id'])
    assert (row.status, row.session_mode) == ('starting', 'papertrade')
    # Like dashboard Start, MCP leaves licensing to the session plugin, with no plan preflight.
    assert jesse.jesse_trade.authorizations == []
    assert _settings_json() == before
    _no_secrets(draft, result)


def test_backup_check_intervals_are_set_per_draft_and_reach_the_engine(jesse):
    draft = _paper(config={'order_backup_check_seconds': 60, 'candle_backup_refresh_seconds': 90})
    assert draft['config']['order_backup_check_seconds'] == 60
    assert draft['config']['candle_backup_refresh_seconds'] == 90

    # null puts the candle refresh back on its automatic interval, and 0 turns the order check off.
    updated = live_service.update_live_draft_service(
        draft['session_id'], config={'candle_backup_refresh_seconds': None, 'order_backup_check_seconds': 0},
    )
    assert updated['config']['candle_backup_refresh_seconds'] is None
    assert updated['config']['order_backup_check_seconds'] == 0

    live_service.start_live_session_service(draft['session_id'])
    [(_function, args)] = jesse.processes.started
    assert args[5]['order_backup_check_seconds'] == 0
    assert args[5]['candle_backup_refresh_seconds'] is None


def test_starting_a_real_draft_sends_its_key_and_the_venue_config(jesse):
    draft = live_service.create_live_draft_service(paper_mode=False, exchange_api_key_id=SPOT_KEY, routes=json.dumps(ROUTES))
    result = live_service.start_live_session_service(draft['session_id'])

    assert result['mode'] == 'live' and 'REAL' in result['trading']
    [(_function, args)] = jesse.processes.started
    assert args[2:4] == ('Binance Spot', SPOT_KEY) and args[-1] == 'livetrade'
    assert args[5]['exchanges']['Binance Spot']['simulation_model'] == 'spot'
    assert _row(draft['session_id']).session_mode == 'livetrade'
    _no_secrets(draft, result)


def test_only_drafts_start_and_a_started_session_is_never_started_twice(jesse):
    draft = _paper()['session_id']
    assert live_service.start_live_session_service(draft)['status'] == 'success'
    plan_requests = len(jesse.jesse_trade.authorizations)

    again = live_service.start_live_session_service(draft)
    assert again['error_type'] == 'not_draft' and len(jesse.processes.started) == 1
    # Refused before asking jesse.trade or reaching /live (which would refuse it again with 409).
    assert len(jesse.jesse_trade.authorizations) == plan_requests
    assert [path for _method, path in jesse.requests].count('/live') == 1
    assert live_service.start_live_session_service(str(uuid.uuid4()))['error_type'] == 'not_found'


def test_a_paper_draft_that_remembers_a_key_starts_without_it(jesse):
    draft = live_service.create_live_draft_service(paper_mode=False, exchange_api_key_id=BYBIT_KEY, routes=json.dumps(ROUTES))
    live_service.update_live_draft_service(draft['session_id'], paper_mode=True, exchange='Bybit USDT Perpetual')
    assert _form(draft['session_id'])['exchange_api_key_id'] == BYBIT_KEY

    result = live_service.start_live_session_service(draft['session_id'])

    assert result['mode'] == 'paper' and result['exchange_api_key'] is None
    [(_function, args)] = jesse.processes.started
    assert args[3] == '' and args[-1] == 'papertrade'


def test_overlapping_updates_of_one_draft_keep_both_changes(jesse, monkeypatch):
    """Each update replaces the stored form, so without LIVE_SESSIONS_LOCK one change would be lost."""
    draft = _paper()['session_id']
    read_settings = live_service._settings

    def slow_settings():
        time.sleep(0.3)  # widens the window between reading the draft and writing it back
        return read_settings()

    monkeypatch.setattr(live_service, '_settings', slow_settings)
    changes = [{'debug_mode': False}, {'data_routes': json.dumps([{'symbol': 'BTC-USDT', 'timeframe': '4h'}])}]
    threads = [threading.Thread(target=live_service.update_live_draft_service, args=(draft,), kwargs=change)
               for change in changes]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(WAIT_SECONDS)

    form = _form(draft)
    assert form['debug_mode'] is False
    assert form['data_routes'] == [{'symbol': 'BTC-USDT', 'timeframe': '4h'}]


def test_overlapping_start_requests_for_one_draft_start_one_process(jesse):
    """Checking the draft and spawning are one critical section across all API callers."""
    import requests

    draft = _paper()['session_id']
    form = _form(draft)
    body = {'id': draft, 'exchange': form['exchange'], 'exchange_api_key_id': '', 'notification_api_key_id': '',
            'routes': form['routes'], 'data_routes': [], 'config': live_engine_config(form['config']),
            'debug_mode': True, 'paper_mode': True}
    jesse.processes.start_delay = 0.3
    statuses = []
    threads = [threading.Thread(target=lambda: statuses.append(requests.post(
        f'{mcp_config.JESSE_API_URL}/live', json=body, headers={'Authorization': AUTH}, timeout=WAIT_SECONDS).status_code))
        for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(WAIT_SECONDS)

    assert sorted(statuses) == [202, 409, 409, 409]
    assert len(jesse.processes.started) == 1


def test_a_stop_never_waits_behind_another_mcp_call(jesse, monkeypatch):
    """Stops remain independent of MCP operations waiting for settings or other HTTP reads."""
    running = _paper()['session_id']
    assert live_service.start_live_session_service(running)['status'] == 'success'
    waiting = _paper()['session_id']
    entered, release = threading.Event(), threading.Event()
    read_settings = live_service._settings

    def held_settings():
        entered.set()
        release.wait(WAIT_SECONDS)  # the start is still inside LIVE_SESSIONS_LOCK
        return read_settings()

    monkeypatch.setattr(live_service, '_settings', held_settings)
    results = {}
    starter = threading.Thread(target=lambda: results.update(start=live_service.start_live_session_service(waiting)))
    starter.start()
    try:
        assert entered.wait(WAIT_SECONDS)
        began = time.monotonic()
        stopped = live_service.stop_live_session_service(running)
        elapsed = time.monotonic() - began
    finally:
        release.set()
        starter.join(WAIT_SECONDS)

    assert stopped['status'] == 'success' and elapsed < 2
    assert jesse.processes.cancelled == [running]
    assert results['start']['status'] == 'success' and waiting in jesse.processes.active


def _start_body(session_id: str, form: dict) -> dict:
    """The dashboard's /live request for a draft form."""
    return {'id': session_id, 'exchange': form['exchange'], 'exchange_api_key_id': '', 'notification_api_key_id': '',
            'routes': form['routes'], 'data_routes': form['data_routes'], 'config': live_engine_config(form['config']),
            'debug_mode': True, 'paper_mode': True}


def test_a_failed_process_launch_leaves_the_draft_as_it_was(jesse):
    """A process launch failure must restore the draft so the user can retry it."""
    session_id = _paper(title='keep me')['session_id']
    columns = ('status', 'session_mode', 'exchange', 'state', 'title', 'finished_at', 'exception', 'updated_at')
    before = [getattr(_row(session_id), column) for column in columns]
    jesse.processes.fail_launch = 'before'

    failed = live_service.start_live_session_service(session_id)

    assert (failed['status'], failed['error_type'], failed['http_status']) == ('error', 'jesse_error', 500)
    assert [getattr(_row(session_id), column) for column in columns] == before
    assert jesse.processes.started == [] and not jesse.processes.active
    # The draft starts normally afterwards.
    assert live_service.start_live_session_service(session_id)['status'] == 'success'
    assert len(jesse.processes.started) == 1


def test_a_failed_launch_of_a_session_without_a_draft_leaves_no_row(jesse):
    import requests

    form = _form(_paper()['session_id'])
    session_id = str(uuid.uuid4())
    jesse.processes.fail_launch = 'before'
    response = requests.post(f'{mcp_config.JESSE_API_URL}/live', json=_start_body(session_id, form),
                             headers={'Authorization': AUTH}, timeout=WAIT_SECONDS)
    assert response.status_code == 500
    assert LiveSession.select().where(LiveSession.id == session_id).count() == 0


def test_a_launch_error_after_the_process_started_never_frees_the_draft_for_a_second_start(jesse):
    """The process may be running, so the row stays "starting" and a second start is refused."""
    session_id = _paper()['session_id']
    jesse.processes.fail_launch = 'after'

    failed = live_service.start_live_session_service(session_id)

    assert failed['http_status'] == 500
    assert _row(session_id).status == 'starting' and session_id in jesse.processes.active
    assert live_service.start_live_session_service(session_id)['error_type'] == 'not_draft'
    assert len(jesse.processes.started) == 1


def test_starts_match_dashboard_without_a_tab_cap_or_plan_preflight(jesse):
    """Tab allowances control dashboard tabs, not authorization for the Start operation."""
    jesse.jesse_trade.status = 503
    jesse.jesse_trade.limits['live_trading_tabs'] = 1
    for _ in range(3):
        draft = _paper()['session_id']
        assert live_service.start_live_session_service(draft)['status'] == 'success'
    assert len(jesse.processes.started) == 3
    assert jesse.jesse_trade.authorizations == []


@pytest.mark.parametrize('operation', ['remove', 'update-state', 'cancel'])
def test_dashboard_mutations_wait_for_start_to_publish_its_worker(jesse, operation):
    """Concurrent callers cannot delete/edit a launching worker or lose a stop before launch."""
    import requests

    draft = _paper()['session_id']
    form = _form(draft)
    jesse.processes.start_delay = 0.5  # Hold the launch window until the competing HTTP request arrives.
    results = {}
    starter = threading.Thread(target=lambda: results.update(start=requests.post(
        f'{mcp_config.JESSE_API_URL}/live', json=_start_body(draft, form),
        headers={'Authorization': AUTH}, timeout=WAIT_SECONDS)))
    starter.start()
    try:
        assert jesse.processes.entered.wait(WAIT_SECONDS)
        if operation == 'remove':
            path, body = f'/live/sessions/{draft}/remove', {}
        elif operation == 'update-state':
            path, body = '/live/update-state', {'id': draft, 'state': {'form': {'changed': True}}, 'require_draft': True}
        else:
            path, body = '/live/cancel', {'id': draft, 'paper_mode': True}
        response = requests.post(f'{mcp_config.JESSE_API_URL}{path}', json=body,
                                 headers={'Authorization': AUTH}, timeout=WAIT_SECONDS)
    finally:
        starter.join(WAIT_SECONDS)
    assert results['start'].status_code == 202
    assert response.status_code == (200 if operation == 'cancel' else 409)
    assert _row(draft).status == 'starting'
    assert 'changed' not in _form(draft)
    assert (draft in jesse.processes.active) == (operation != 'cancel')


def test_draft_only_save_cannot_overwrite_an_ended_session_but_dashboard_can(jesse):
    """A stale MCP edit must not become an autosave of a session started since its first read."""
    import requests

    draft = _paper()['session_id']
    assert live_service.start_live_session_service(draft)['status'] == 'success'
    assert live_service.stop_live_session_service(draft)['status'] == 'success'
    LiveSession.update(status='stopped').where(LiveSession.id == draft).execute()
    body = {'id': draft, 'state': {'form': {'ended_tab': True}}, 'require_draft': True}
    refused = requests.post(f'{mcp_config.JESSE_API_URL}/live/update-state', json=body,
                            headers={'Authorization': AUTH}, timeout=WAIT_SECONDS)
    assert refused.status_code == 409 and 'ended_tab' not in _form(draft)
    body.pop('require_draft')
    saved = requests.post(f'{mcp_config.JESSE_API_URL}/live/update-state', json=body,
                          headers={'Authorization': AUTH}, timeout=WAIT_SECONDS)
    assert saved.status_code == 200 and _form(draft)['ended_tab'] is True


def test_stop_asks_the_session_to_end_and_describes_what_the_plugin_does(jesse):
    draft = _paper()['session_id']
    not_running = live_service.stop_live_session_service(draft)
    assert (not_running['error_type'], not_running['session_status']) == ('not_running', 'draft')
    assert jesse.processes.cancelled == []

    live_service.start_live_session_service(draft)
    result = live_service.stop_live_session_service(draft)

    assert result['status'] == 'success' and result['action'] == 'live_session_stop_requested'
    assert result['mode'] == 'paper' and result['on_stop'] == live_service.STOP_SEMANTICS
    assert 'closes their open positions' in result['on_stop'] and 'persistency on leaves' in result['on_stop']
    assert jesse.processes.cancelled == [draft] and draft not in jesse.processes.active
    assert ('POST', '/live/cancel') in jesse.requests
    # The session record now reconciles to stopped exactly like the dashboard's view.
    assert live_service.stop_live_session_service(draft)['error_type'] == 'not_running'
    assert _row(draft).status == 'stopped'


def test_restart_is_copy_then_start_and_leaves_the_old_session_alone(jesse):
    original = _paper(exchange='Bybit USDT Perpetual', config=json.dumps({'warm_up_candles': 77}))
    session_id = original['session_id']
    live_service.start_live_session_service(session_id)
    live_service.stop_live_session_service(session_id)
    # As in production, the running plugin stores the form without a config (live_mode.run).
    stored = _form(session_id)
    stored.pop('config')
    LiveSession.update(state=json.dumps({'form': stored}), status='stopped').where(LiveSession.id == session_id).execute()

    copy = live_service.copy_live_session_service(session_id, title='rerun')

    assert copy['status'] == 'success' and copy['source_session_id'] == session_id and copy['session_id'] != session_id
    assert (copy['mode'], copy['exchange'], copy['routes']) == ('paper', 'Bybit USDT Perpetual', ROUTES)
    # Without a stored config the dashboard resolves the exchange default again, and so does MCP.
    assert copy['config']['warm_up_candles'] == 300
    assert _row(copy['session_id']).title == 'rerun' and _row(copy['session_id']).status == 'draft'
    assert _row(session_id).status == 'stopped'
    assert live_service.start_live_session_service(copy['session_id'])['status'] == 'success'
    assert [args[0] for _function, args in jesse.processes.started] == [session_id, copy['session_id']]


def test_copying_a_starting_session_keeps_its_engine_config(jesse):
    original = _paper(config=json.dumps({'warm_up_candles': 77, 'exchange': {'balance': 321}}))
    live_service.start_live_session_service(original['session_id'])  # /live stores the engine-shaped config

    copy = live_service.copy_live_session_service(original['session_id'])

    assert copy['config']['warm_up_candles'] == 77 and copy['config']['exchange']['balance'] == 321
    assert copy['config']['exchange']['name'] == 'Binance Perpetual Futures'


def test_a_copy_is_refused_when_its_saved_key_is_gone(jesse):
    live = live_service.create_live_draft_service(paper_mode=False, exchange_api_key_id=BYBIT_KEY, routes=json.dumps(ROUTES))
    ExchangeApiKeys.delete().where(ExchangeApiKeys.id == BYBIT_KEY).execute()
    result = live_service.copy_live_session_service(live['session_id'])
    assert result['error_type'] == 'key_not_found' and LiveSession.select().count() == 1
    assert live_service.start_live_session_service(live['session_id'])['error_type'] == 'key_not_found'
    assert jesse.processes.started == []


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def test_delete_refuses_active_sessions_and_open_dashboard_tabs(jesse):
    import requests

    running = _paper()['session_id']
    live_service.start_live_session_service(running)
    refused = live_service.delete_live_session_service(running)
    assert (refused['error_type'], refused['session_status']) == ('session_active', 'starting')

    tabbed = _paper()['session_id']
    added = requests.post(f'{mcp_config.JESSE_API_URL}/tabs/add', json={'module': 'live', 'id': tabbed},
                          headers={'Authorization': AUTH}, timeout=WAIT_SECONDS)
    assert added.status_code == 200
    assert live_service.delete_live_session_service(tabbed)['error_type'] == 'open_in_dashboard_tab'

    live_service.stop_live_session_service(running)
    deleted = live_service.delete_live_session_service(running)
    assert deleted['status'] == 'success' and 'never affected the exchange' in deleted['message']
    assert LiveSession.select().where(LiveSession.id == running).count() == 0
    assert LiveSession.select().where(LiveSession.id == tabbed).count() == 1
    assert live_service.delete_live_session_service(running)['error_type'] == 'not_found'


# ---------------------------------------------------------------------------
# Isolation, concurrency, and the MCP layer
# ---------------------------------------------------------------------------

def test_concurrent_drafts_keep_their_own_configs_and_never_touch_shared_settings(jesse):
    before = _settings_json()
    requests_made = [
        {'paper_mode': True, 'exchange': 'Binance Perpetual Futures', 'config': json.dumps({'exchange': {'balance': 1001}})},
        {'paper_mode': True, 'exchange': 'Bybit USDT Perpetual', 'config': json.dumps({'exchange': {'balance': 1002}})},
        {'paper_mode': False, 'exchange_api_key_id': SPOT_KEY, 'config': json.dumps({'exchange': {'balance': 1003}})},
        {'paper_mode': False, 'exchange_api_key_id': BYBIT_KEY, 'config': json.dumps({'exchange': {'balance': 1004}})},
        {'paper_mode': True, 'exchange': 'Binance Spot', 'config': json.dumps({'exchange': {'balance': 1005}})},
        {'paper_mode': True, 'exchange': 'Bybit USDT Perpetual', 'config': json.dumps({'warm_up_candles': 11})},
    ]

    async def create_all():
        from jesse.mcp.tools.offload import run_blocking
        results = [None] * len(requests_made)

        async def one(index, arguments):
            results[index] = await run_blocking(live_service.create_live_draft_service, routes=json.dumps(ROUTES), **arguments)

        async with anyio.create_task_group() as group:
            for index, arguments in enumerate(requests_made):
                group.start_soon(one, index, arguments)
        return results

    results = anyio.run(create_all)

    assert all(result['status'] == 'success' for result in results), results
    expected = [('Binance Perpetual Futures', 1001), ('Bybit USDT Perpetual', 1002), ('Binance Spot', 1003),
                ('Bybit USDT Perpetual', 1004), ('Binance Spot', 1005), ('Bybit USDT Perpetual', 777)]
    stored = [(_form(r['session_id'])['config']['exchange']['name'], _form(r['session_id'])['config']['exchange']['balance'])
              for r in results]
    assert stored == expected
    assert _form(results[5]['session_id'])['config']['warm_up_candles'] == 11
    assert _form(results[1]['session_id'])['config']['warm_up_candles'] == 300
    assert len({r['session_id'] for r in results}) == 6 and _settings_json() == before


def test_live_tools_run_through_fastmcp_and_validate_arguments_first(jesse, caplog):
    caplog.set_level(logging.INFO)
    mcp = create_mcp_server(0)

    async def call(name, arguments):
        content = await mcp.call_tool(name, arguments)
        blocks = content[0] if isinstance(content, tuple) else content
        return json.loads(blocks[0].text)

    async def scenario():
        draft = await call('create_live_draft', {'paper_mode': False, 'exchange_api_key_id': BYBIT_KEY,
                                                 'routes': json.dumps(ROUTES), 'notification_api_key_id': TELEGRAM_KEY})
        started = await call('start_live_session', {'session_id': draft['session_id']})
        stopped = await call('stop_live_session', {'session_id': draft['session_id']})
        missing_mode = await call('create_live_draft', {'routes': json.dumps(ROUTES)})  # paper_mode is required
        return draft, started, stopped, missing_mode

    draft, started, stopped, missing_mode = anyio.run(scenario)
    assert (draft['mode'], started['mode'], stopped['mode']) == ('live', 'live', 'live')
    assert (missing_mode['status'], missing_mode['error_type']) == ('error', 'invalid_request')
    assert 'paper_mode is required' in missing_mode['message']
    assert jesse.processes.cancelled == [draft['session_id']]
    _no_secrets(draft, started, stopped, [record.getMessage() for record in caplog.records])


# A number-only value, like a Telegram chat ID pasted into a key ID field.
NUMERIC_SENTINEL = 98765432101234


@pytest.mark.parametrize('tool, arguments', [
    ('create_live_draft', {'routes': ROUTES, 'exchange_api_key_id': FAKE_API_SECRET}),  # paper_mode missing
    ('create_live_draft', {'paper_mode': False, 'exchange_api_key_id': FAKE_API_SECRET}),  # routes missing
    ('create_live_draft', {'paper_mode': 'maybe', 'routes': ROUTES, 'exchange_api_key_id': FAKE_API_SECRET}),
    ('create_live_draft', {'paper_mode': False, 'routes': ROUTES,
                           'exchange_api_key_id': {'api_key': FAKE_API_KEY, 'api_secret': FAKE_API_SECRET}}),
    ('create_live_draft', {'paper_mode': False, 'routes': ROUTES, 'exchange_api_key_id': SPOT_KEY,
                           'notification_api_key_id': [FAKE_BOT_TOKEN]}),
    ('create_live_draft', {'paper_mode': True, 'exchange': 'Binance Spot', 'routes': ROUTES,
                           'notification_api_key_id': NUMERIC_SENTINEL}),
    ('create_live_draft', {'paper_mode': False, 'routes': ROUTES, 'config': [FAKE_API_SECRET],
                           'exchange_api_key_id': FAKE_PASSPHRASE}),
    ('update_live_draft', {'exchange_api_key_id': FAKE_API_SECRET}),  # session_id missing
    ('update_live_draft', {'session_id': SPOT_KEY, 'exchange_api_key_id': {'secret': FAKE_API_SECRET}}),
    ('update_live_draft', {'session_id': SPOT_KEY, 'notification_api_key_id': NUMERIC_SENTINEL}),
])
def test_fastmcp_argument_errors_never_quote_a_misplaced_secret(jesse, caplog, tool, arguments):
    """
    FastMCP's pydantic errors can quote the full input for missing or wrong-typed arguments.
    Service-level validation must keep misplaced secrets out of responses and logs.
    """
    caplog.set_level(logging.DEBUG)
    mcp = create_mcp_server(0)

    async def call():
        content = await mcp.call_tool(tool, arguments)
        blocks = content[0] if isinstance(content, tuple) else content
        return json.loads(blocks[0].text)

    result = anyio.run(call)

    assert (result['status'], result['error_type']) == ('error', 'invalid_request'), result
    logged = [record.getMessage() for record in caplog.records]
    _no_secrets(result, logged)
    assert str(NUMERIC_SENTINEL) not in json.dumps([result, logged])
    # Refused before any request reached Jesse.
    assert jesse.requests == [] and LiveSession.select().count() == 0


def test_agent_guidance_describes_live_management_and_never_promises_closed_positions():
    """Agent guidance must expose the supported live-session lifecycle."""
    from jesse.mcp import server as mcp_server
    from jesse.mcp.agent_rules import _load_packaged_rules
    from jesse.mcp.resources import register_resources

    class _Resources:
        def __init__(self):
            self.resources = {}

        def resource(self, uri):
            def decorator(func):
                self.resources[uri] = func
                return func
            return decorator

    holder = _Resources()
    register_resources(holder)
    guide = ' '.join(holder.resources['jesse://live_trading']().split())
    rules = ' '.join(_load_packaged_rules().split())
    analysis = ' '.join(holder.resources['jesse://session_analysis']().split())

    assert 'read-only through MCP' not in rules and 'tell the user to use the dashboard' not in analysis
    for text in (guide, rules):
        assert 'only when the user asks' in text
        assert 'persistency on leaves' in text or 'with `persistency` on leaves' in text
    assert 'Never say a stop closed positions' in rules
    assert 'no order placement' in guide.lower() and 'no order placement' in rules.lower()
    assert 'jesse://live_trading' in rules and 'jesse://live_trading' in mcp_server.INSTRUCTIONS
    assert 'Live and paper sessions do not use research credits' in guide


def test_json_arguments_work_as_text_or_as_objects_through_fastmcp(jesse):
    """FastMCP decodes JSON text for non-str parameters; both decoded and text forms must work."""
    mcp = create_mcp_server(0)

    async def call(name, arguments):
        content = await mcp.call_tool(name, arguments)
        blocks = content[0] if isinstance(content, tuple) else content
        return json.loads(blocks[0].text)

    async def scenario():
        as_text = await call('create_live_draft', {'paper_mode': True, 'exchange': 'Binance Spot', 'routes': json.dumps(ROUTES),
                                                   'data_routes': json.dumps([{'symbol': 'BTC-USDT', 'timeframe': '4h'}]),
                                                   'config': json.dumps({'warm_up_candles': 99})})
        as_objects = await call('create_live_draft', {'paper_mode': True, 'exchange': 'Binance Spot', 'routes': ROUTES,
                                                      'config': {'exchange': {'balance': 55}}})
        updated = await call('update_live_draft', {'session_id': as_text['session_id'],
                                                   'routes': json.dumps([{'strategy': 'Other', 'symbol': 'ETH-USDT', 'timeframe': '1h'}]),
                                                   'config': json.dumps({'persistency': False})})
        return as_text, as_objects, updated

    as_text, as_objects, updated = anyio.run(scenario)
    assert as_text['status'] == 'success' and as_text['config']['warm_up_candles'] == 99
    assert as_text['data_routes'] == [{'symbol': 'BTC-USDT', 'timeframe': '4h'}]
    assert as_objects['status'] == 'success' and as_objects['config']['exchange']['balance'] == 55
    assert updated['status'] == 'success' and updated['routes'][0]['symbol'] == 'ETH-USDT'
    assert updated['config']['persistency'] is False and updated['config']['warm_up_candles'] == 99


# ---------------------------------------------------------------------------
# Restart and where money settings come from
# ---------------------------------------------------------------------------

def _live_futures(**overrides) -> dict:
    arguments = {'paper_mode': False, 'exchange_api_key_id': BYBIT_KEY, 'routes': json.dumps(ROUTES),
                 'config': json.dumps({'exchange': {'futures_leverage': 12, 'futures_leverage_mode': 'cross'}})}
    arguments.update(overrides)
    return live_service.create_live_draft_service(**arguments)


def _ran_and_stopped(session_id: str) -> None:
    """Start a draft, save it the way the running live plugin does (live_mode.run), then stop it."""
    assert live_service.start_live_session_service(session_id)['status'] == 'success'
    form = _form(session_id)
    live_session_repository.store_live_session(
        id=session_id, status='running', session_mode=_row(session_id).session_mode, exchange=form['exchange'],
        state={'form': {key: form[key] for key in ('debug_mode', 'paper_mode', 'exchange_api_key_id',
                                                   'notification_api_key_id', 'exchange', 'routes', 'data_routes')}},
    )
    live_service.stop_live_session_service(session_id)
    LiveSession.update(status='stopped').where(LiveSession.id == session_id).execute()


def test_a_session_that_ran_keeps_its_config_when_the_plugin_saves_it_again(jesse):
    session_id = _live_futures()['session_id']

    _ran_and_stopped(session_id)

    exchange = _form(session_id)['config']['exchanges']['Bybit USDT Perpetual']
    assert (exchange['futures_leverage'], exchange['futures_leverage_mode']) == (12, 'cross')


def test_restart_runs_an_ended_session_again_with_its_exact_settings(jesse):
    original = _live_futures(title='BTC trend')
    session_id = original['session_id']
    _ran_and_stopped(session_id)

    result = live_service.restart_live_session_service(session_id)

    assert result['status'] == 'success' and result['action'] == 'live_session_restarted', result
    new_id = result['session_id']
    assert new_id != session_id and result['restarted_from'] == session_id
    assert (result['mode'], result['exchange'], result['routes']) == ('live', 'Bybit USDT Perpetual', ROUTES)
    assert result['exchange_api_key']['id'] == BYBIT_KEY
    assert result['config']['exchange']['futures_leverage'] == 12
    assert result['config_source'] == {'exchange.futures_leverage': 'copied', 'exchange.futures_leverage_mode': 'copied'}
    assert 'config_warnings' not in result
    assert [args[0] for _function, args in jesse.processes.started] == [session_id, new_id]
    assert _row(new_id).title == 'BTC trend' and _row(session_id).status == 'stopped'
    _no_secrets(result)


def test_restart_refuses_a_running_session_and_a_draft(jesse):
    draft = _live_futures()['session_id']
    refused = live_service.restart_live_session_service(draft)
    assert (refused['error_type'], refused['session_status']) == ('is_draft', 'draft')

    live_service.start_live_session_service(draft)
    running = live_service.restart_live_session_service(draft)
    assert running['error_type'] == 'session_active' and 'never stops one' in running['message']
    assert jesse.processes.cancelled == [] and len(jesse.processes.started) == 1


def test_restart_refuses_when_these_routes_already_run_on_the_key(jesse):
    ended = _live_futures()['session_id']
    _ran_and_stopped(ended)
    already = live_service.restart_live_session_service(ended)['session_id']

    again = live_service.restart_live_session_service(ended)

    assert again['error_type'] == 'routes_already_running' and again['running_session_id'] == already
    assert len(jesse.processes.started) == 2


def test_restart_does_not_start_a_copy_whose_money_settings_were_lost(jesse):
    session_id = _live_futures()['session_id']
    _ran_and_stopped(session_id)
    # A session that ran before Jesse kept its config: its stored form has none.
    stored = _form(session_id)
    stored.pop('config')
    LiveSession.update(state=json.dumps({'form': stored})).where(LiveSession.id == session_id).execute()

    result = live_service.restart_live_session_service(session_id)

    assert result['error_type'] == 'settings_not_copied', result
    assert result['config_source']['exchange.futures_leverage'] == 'saved_default'
    assert 'NOT started' in result['message'] and 'futures_leverage 7' in result['message']
    assert _row(result['draft_session_id']).status == 'draft'
    assert len(jesse.processes.started) == 1


def test_a_new_draft_for_routes_that_already_ran_points_to_restart(jesse):
    ended = _live_futures()['session_id']
    _ran_and_stopped(ended)

    draft = _live_futures(config=None)

    assert draft['status'] == 'success'
    assert draft['earlier_session']['session_id'] == ended and draft['earlier_session']['is_active'] is False
    assert draft['earlier_session']['money_settings_that_differ'] == {
        'futures_leverage': {'earlier': 12, 'this_draft': 7}}
    warning = draft['config_warnings'][-1]
    assert f'restart_live_session("{ended}")' in warning and 'futures_leverage 7 (it had 12)' in warning

    other_routes = _live_futures(routes=json.dumps([{**ROUTES[0], 'symbol': 'ETH-USDT'}]))
    assert 'earlier_session' not in other_routes and 'config_warnings' not in other_routes


def test_a_new_draft_warns_when_the_same_routes_are_running_on_the_key(jesse):
    running = _live_futures()['session_id']
    live_service.start_live_session_service(running)

    draft = _live_futures()

    assert draft['earlier_session']['session_id'] == running and draft['earlier_session']['is_active'] is True
    assert 'trade the same symbols twice on one account' in draft['config_warnings'][-1]


def test_drafts_say_where_their_money_settings_came_from(jesse):
    saved = _paper(exchange='Bybit USDT Perpetual')
    assert set(saved['config_source'].values()) == {'saved_default'} and 'config_warnings' not in saved

    nothing_saved = _paper(exchange='KuCoin USDT Perpetual')
    assert nothing_saved['config_source'] == {
        'exchange.balance': 'hard_default', 'exchange.fee': 'exchange_default',
        'exchange.futures_leverage': 'hard_default', 'exchange.futures_leverage_mode': 'hard_default'}
    assert nothing_saved['config_warnings'] == [
        "leverage 5 is Jesse's built-in default: nothing is saved for paper sessions on KuCoin USDT Perpetual. "
        'Set config.exchange.futures_leverage to choose it.']

    chosen = _paper(exchange='KuCoin USDT Perpetual', config=json.dumps({'exchange': {'futures_leverage': 3}}))
    assert chosen['config_source']['exchange.futures_leverage'] == 'explicit'
    assert 'config_warnings' not in chosen

    updated = live_service.update_live_draft_service(chosen['session_id'], debug_mode=False)
    assert updated['config_source']['exchange.futures_leverage'] == 'stored'
    copied = live_service.copy_live_session_service(chosen['session_id'])
    assert copied['config_source']['exchange.futures_leverage'] == 'copied'
