"""
The Jesse API routes that call jesse.trade (strategy catalog, strategy import, and the
LICENSE_API_TOKEN exchange) run in FastAPI's threadpool.

Jesse's real strategy and auth routers are served by uvicorn on a loopback port, and a local
stand-in for jesse.trade's api2 answers their outgoing requests over real HTTP, so the event
loop, the threadpool, and `requests` behave as they do in `jesse run`. The tests pin what each
route sends and returns (parity with the handlers' documented responses), that dashboard
authentication and the licensing checks still apply, that a slow jesse.trade no longer holds
up other requests, and that overlapping imports of one class name cannot both succeed.
"""
import inspect
import json
import os
import socket
import threading
import time
from hashlib import sha256
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qsl, urlsplit

import pytest
import requests
import uvicorn
from fastapi import FastAPI
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from jesse.controllers import auth_controller, strategy_controller
from jesse.services import auth
from jesse.services import strategy_handler

PASSWORD = 'jesse-trade-routes-password'
DASHBOARD_AUTH = {'Authorization': sha256(PASSWORD.encode('utf-8')).hexdigest()}
LICENSE = 'fake-license-token-for-tests'
# What the stand-in hands out for LICENSE; strategy code is only returned with this bearer,
# the way jesse.trade withholds code from guests and from plans without access.
SESSION_TOKEN = 'fake-jesse-trade-session-token'
USER = {'username': 'tester', 'plan': 'free'}
SLUG = 'demo-strategy'
CLASS_NAME = 'DemoImported'
# Long enough that a blocked event loop is unmistakable, short of the routes' 10 s timeout.
HOLD_SECONDS = 5
# A probe on a free event loop answers in milliseconds; anything near HOLD_SECONDS means it
# waited for the held jesse.trade request.
RESPONSIVE_SECONDS = 1.5
# Upper bound for server startup and any single request, so a regression fails instead of hanging.
WAIT_SECONDS = 15


def _code(class_name: str, marker: str = '') -> str:
    return f'from jesse.strategies import Strategy\n\n\nclass {class_name}(Strategy):\n    pass  # {marker}\n'


class _JesseTrade:
    """
    Local stand-in for jesse.trade's api2. By default it behaves like the real service for
    these routes: the license exchange accepts only LICENSE, and a strategy's code is returned
    only to SESSION_TOKEN. `replies[(method, path)] = (status, text)` overrides one endpoint;
    paths in `hold` wait for `release` before answering. Every request is recorded.
    """

    def __init__(self) -> None:
        self.requests: list = []
        self.replies: dict = {}
        self.codes: dict = {SLUG: _code(CLASS_NAME)}
        self.hold: set = set()
        self.release = threading.Event()
        self.arrived = threading.Condition()
        backend = self

        class Handler(BaseHTTPRequestHandler):
            def _handle(self, method: str) -> None:
                parts = urlsplit(self.path)
                length = int(self.headers.get('Content-Length') or 0)
                body = json.loads(self.rfile.read(length)) if length else None
                with backend.arrived:
                    backend.requests.append({
                        'method': method, 'path': parts.path, 'query': dict(parse_qsl(parts.query)),
                        'authorization': self.headers.get('Authorization'), 'json': body,
                    })
                    backend.arrived.notify_all()
                if parts.path in backend.hold:
                    backend.release.wait(HOLD_SECONDS)
                status, text = backend.reply(method, parts.path, self.headers.get('Authorization'), body)
                payload = text.encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self) -> None:
                self._handle('GET')

            def do_POST(self) -> None:
                self._handle('POST')

            def log_message(self, *_args) -> None:
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.url = f'http://127.0.0.1:{self.server.server_address[1]}'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def reply(self, method: str, path: str, authorization: Optional[str], body) -> tuple:
        if (method, path) in self.replies:
            return self.replies[(method, path)]
        if (method, path) == ('POST', '/auth/exchange-token'):
            if (body or {}).get('license_api_token') == LICENSE:
                return 200, json.dumps({'access_token': SESSION_TOKEN, 'user': USER})
            return 401, json.dumps({'message': 'Invalid license API token'})
        if (method, path) == ('GET', '/strategies/periods'):
            return 200, json.dumps(['Q4 of 2025', 'Q1 of 2026'])
        if (method, path) == ('GET', '/strategies'):
            return 200, json.dumps({'data': [{'slug': SLUG}], 'total': 1})
        slug = path.removeprefix('/strategies/')
        if method == 'GET' and slug.endswith('/metrics'):
            return 200, json.dumps({'sharpe_ratio': 1.25, 'slug': slug.removesuffix('/metrics')})
        if method == 'GET' and slug in self.codes:
            unlocked = authorization == f'Bearer {SESSION_TOKEN}'
            return 200, json.dumps({'slug': slug, 'name': slug, 'code': self.codes[slug] if unlocked else None})
        return 404, json.dumps({'message': 'Not found'})

    def wait_for(self, count: int) -> None:
        """Block until `count` requests have arrived."""
        with self.arrived:
            assert self.arrived.wait_for(lambda: len(self.requests) >= count, WAIT_SECONDS), self.requests

    def __enter__(self) -> '_JesseTrade':
        self.thread.start()
        return self

    def __exit__(self, *_exc) -> None:
        self.release.set()
        self.server.shutdown()
        self.server.server_close()


class _Jesse:
    """Jesse's real strategy and auth routers under uvicorn on a loopback port, plus a probe route."""

    def __init__(self) -> None:
        app = FastAPI()

        # The same handler jesse/__init__.py registers on the real app: a failed dashboard
        # authentication becomes this 401 response.
        @app.exception_handler(auth.InvalidAuthError)
        async def invalid_auth_handler(_request, _exc):
            return auth.unauthorized_response()

        # An async route: it answers only while the event loop is free.
        @app.get('/probe')
        async def probe():
            return {'ok': True}

        app.include_router(strategy_controller.router)
        app.include_router(auth_controller.router)
        self.app = app
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.bind(('127.0.0.1', 0))
        self.url = f'http://127.0.0.1:{self._socket.getsockname()[1]}'
        self.server = uvicorn.Server(uvicorn.Config(app, log_level='warning', access_log=False))
        self.thread = threading.Thread(target=self.server.run, kwargs={'sockets': [self._socket]}, daemon=True)

    def request(self, method: str, path: str, headers: Optional[dict] = None, **kwargs) -> requests.Response:
        return requests.request(method, self.url + path, headers={**DASHBOARD_AUTH, **(headers or {})},
                                timeout=WAIT_SECONDS, **kwargs)

    def __enter__(self) -> '_Jesse':
        self.thread.start()
        deadline = time.monotonic() + WAIT_SECONDS
        while not self.server.started:
            assert self.thread.is_alive() and time.monotonic() < deadline, 'test server failed to start'
            time.sleep(0.01)
        return self

    def __exit__(self, *_exc) -> None:
        self.server.should_exit = True
        self.thread.join(WAIT_SECONDS)
        self._socket.close()


@pytest.fixture
def project(tmp_path, monkeypatch) -> Path:
    """A disposable Jesse project; the strategy handler resolves strategies/ from the working directory."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'strategies').mkdir()
    return tmp_path


@pytest.fixture
def jesse_trade(monkeypatch):
    with _JesseTrade() as backend:
        monkeypatch.setattr(strategy_controller, 'JESSE_API2_URL', backend.url)
        monkeypatch.setattr(auth_controller, 'JESSE_API2_URL', backend.url)
        yield backend


@pytest.fixture
def jesse(project, jesse_trade, monkeypatch):
    monkeypatch.setitem(auth.ENV_VALUES, 'PASSWORD', PASSWORD)
    monkeypatch.setitem(auth_controller.ENV_VALUES, 'LICENSE_API_TOKEN', LICENSE)
    with _Jesse() as server:
        yield server


# Each route: the Jesse request, the jesse.trade request it makes, and the prefix of its
# error message when jesse.trade answers with an error status.
ROUTES = {
    'index': {
        'call': ('GET', '/strategy/index', {'params': {'period': 'Q1 of 2026', 'sort_by': 'PNL',
                                                       'submitted_after': '2025-01-01', 'submitted_before': '2026-01-01'}}),
        'upstream': ('GET', '/strategies'),
        'query': {'period': 'Q1 of 2026', 'sort_by': 'PNL', 'submitted_after': '2025-01-01', 'submitted_before': '2026-01-01'},
        'failure': 'Failed to fetch strategies: ',
    },
    'periods': {
        'call': ('GET', '/strategy/periods', {}),
        'upstream': ('GET', '/strategies/periods'),
        'query': {},
        'failure': 'Failed to fetch periods: ',
    },
    'strategy': {
        'call': ('GET', f'/strategy/jesse-trade/{SLUG}', {}),
        'upstream': ('GET', f'/strategies/{SLUG}'),
        'query': {},
        'failure': 'Failed to fetch strategy: ',
    },
    'metrics': {
        'call': ('GET', f'/strategy/jesse-trade/{SLUG}/metrics',
                 {'params': {'period': 'Q1 of 2026', 'symbol': 'ETH-USDT', 'timeframe': '1h'}}),
        'upstream': ('GET', f'/strategies/{SLUG}/metrics'),
        'query': {'period': 'Q1 of 2026', 'symbol': 'ETH-USDT', 'timeframe': '1h'},
        'failure': 'Failed to fetch strategy metrics: ',
    },
    'import': {
        'call': ('POST', '/strategy/import', {'json': {'slug': SLUG}}),
        'upstream': ('GET', f'/strategies/{SLUG}'),
        'query': {},
        'failure': 'Failed to fetch strategy: ',
    },
    'token': {
        'call': ('POST', '/auth/jesse-trade-token', {}),
        'upstream': ('POST', '/auth/exchange-token'),
        'query': {},
        'failure': 'Failed to exchange token: ',
    },
}
# Routes that forward the dashboard's X-Jesse-Trade-Token to jesse.trade as a bearer token.
FORWARDS_TOKEN = {'index', 'strategy', 'metrics', 'import'}


def _call(jesse: _Jesse, route: str, jesse_trade_token: Optional[str] = SESSION_TOKEN, **overrides) -> requests.Response:
    method, path, kwargs = ROUTES[route]['call']
    headers = {'X-Jesse-Trade-Token': jesse_trade_token} if jesse_trade_token else {}
    return jesse.request(method, path, headers={**headers, **overrides.pop('headers', {})}, **{**kwargs, **overrides})


def _expected_success(route: str) -> dict:
    """What each route returns for the stand-in's default answer."""
    if route == 'token':
        return {'status': 'success', 'access_token': SESSION_TOKEN, 'user': USER}
    if route == 'import':
        return {'status': 'success', 'message': f'Strategy "{CLASS_NAME}" has been imported.',
                'path': f'strategies/{CLASS_NAME}', 'name': CLASS_NAME}
    if route == 'index':
        return {'data': [{'slug': SLUG}], 'total': 1}
    if route == 'periods':
        return ['Q4 of 2025', 'Q1 of 2026']
    if route == 'strategy':
        return {'slug': SLUG, 'name': SLUG, 'code': _code(CLASS_NAME)}
    return {'sharpe_ratio': 1.25, 'slug': SLUG}


def test_every_jesse_trade_route_is_a_threadpool_handler():
    """FastAPI runs a plain `def` endpoint in its threadpool and an `async def` one on the event loop."""
    endpoints = {route.path: route.endpoint for app_router in (strategy_controller.router, auth_controller.router)
                 for route in app_router.routes}
    for spec in ROUTES.values():
        path = spec['call'][1].replace(SLUG, '{slug}')
        assert not inspect.iscoroutinefunction(endpoints[path]), path


# An import without a session token is the licensing refusal, covered separately below.
@pytest.mark.parametrize(('route', 'with_token'), [(route, with_token) for route in ROUTES for with_token in (True, False)
                                                   if (route, with_token) != ('import', False)])
def test_requests_and_successful_responses_are_unchanged(jesse, jesse_trade, project, route, with_token):
    if route == 'strategy' and not with_token:
        # A guest sees the listing without code, exactly as jesse.trade returns it.
        expected = {'slug': SLUG, 'name': SLUG, 'code': None}
    else:
        expected = _expected_success(route)

    response = _call(jesse, route, jesse_trade_token=SESSION_TOKEN if with_token else None)

    assert (response.status_code, response.json()) == (200, expected)
    [sent] = jesse_trade.requests
    method, path = ROUTES[route]['upstream']
    assert (sent['method'], sent['path'], sent['query']) == (method, path, ROUTES[route]['query'])
    forwarded = f'Bearer {SESSION_TOKEN}' if with_token and route in FORWARDS_TOKEN else None
    assert sent['authorization'] == forwarded
    # Only the license exchange sends a body, and it carries only the project's license token.
    assert sent['json'] == ({'license_api_token': LICENSE} if route == 'token' else None)
    if route == 'import':
        assert (project / 'strategies' / CLASS_NAME / '__init__.py').read_text() == _code(CLASS_NAME)


@pytest.mark.parametrize('route', ROUTES)
def test_jesse_trade_error_status_and_text_are_relayed(jesse, jesse_trade, project, route):
    jesse_trade.replies[ROUTES[route]['upstream']] = (503, '{"message": "maintenance"}')

    response = _call(jesse, route)

    assert response.status_code == 503
    assert response.json() == {'status': 'error', 'message': ROUTES[route]['failure'] + '{"message": "maintenance"}'}
    assert os.listdir(project / 'strategies') == []


@pytest.mark.parametrize('route', ROUTES)
def test_unreachable_jesse_trade_is_a_500(jesse, jesse_trade, project, route, monkeypatch):
    with socket.socket() as closed:
        closed.bind(('127.0.0.1', 0))
        closed_url = f'http://127.0.0.1:{closed.getsockname()[1]}'
    monkeypatch.setattr(strategy_controller, 'JESSE_API2_URL', closed_url)
    monkeypatch.setattr(auth_controller, 'JESSE_API2_URL', closed_url)

    response = _call(jesse, route)

    assert response.status_code == 500
    assert response.json()['status'] == 'error'
    assert response.json()['message'].startswith('Error connecting to jesse.trade: ')
    assert os.listdir(project / 'strategies') == []


@pytest.mark.parametrize('route', ROUTES)
@pytest.mark.parametrize('authorization', [None, 'wrong-token', PASSWORD])
def test_dashboard_authentication_is_still_required(jesse, jesse_trade, project, route, authorization):
    method, path, kwargs = ROUTES[route]['call']
    headers = {'X-Jesse-Trade-Token': SESSION_TOKEN}
    if authorization:
        headers['Authorization'] = authorization

    response = requests.request(method, jesse.url + path, headers=headers, timeout=WAIT_SECONDS, **kwargs)

    assert (response.status_code, response.json()) == (401, {'message': 'Invalid password'})
    assert jesse_trade.requests == []
    assert os.listdir(project / 'strategies') == []


@pytest.mark.parametrize('license_token', [None, ''])
def test_a_missing_license_token_is_refused_without_contacting_jesse_trade(jesse, jesse_trade, monkeypatch, license_token):
    if license_token is None:
        monkeypatch.delitem(auth_controller.ENV_VALUES, 'LICENSE_API_TOKEN')
    else:
        monkeypatch.setitem(auth_controller.ENV_VALUES, 'LICENSE_API_TOKEN', license_token)

    response = _call(jesse, 'token')

    assert (response.status_code, response.json()) == (
        400, {'status': 'error', 'message': 'LICENSE_API_TOKEN not found in .env file'})
    assert jesse_trade.requests == []


def test_a_rejected_license_token_is_relayed_as_a_failure(jesse, jesse_trade, monkeypatch):
    monkeypatch.setitem(auth_controller.ENV_VALUES, 'LICENSE_API_TOKEN', 'revoked-license-token')

    response = _call(jesse, 'token')

    assert (response.status_code, response.json()) == (
        401, {'status': 'error', 'message': 'Failed to exchange token: {"message": "Invalid license API token"}'})
    assert [r['json'] for r in jesse_trade.requests] == [{'license_api_token': 'revoked-license-token'}]
    assert 'access_token' not in response.json()


@pytest.mark.parametrize('jesse_trade_token', [None, 'expired-or-foreign-session-token'])
def test_import_without_access_to_the_code_writes_nothing(jesse, jesse_trade, project, jesse_trade_token):
    response = _call(jesse, 'import', jesse_trade_token=jesse_trade_token)

    assert (response.status_code, response.json()) == (403, {
        'status': 'error', 'message': 'Strategy code not available. You may not have access to this strategy.'})
    assert os.listdir(project / 'strategies') == []


def test_import_refusals_for_classless_code_and_an_existing_strategy(jesse, jesse_trade, project):
    jesse_trade.codes['no-class'] = 'print("no strategy here")\n'
    classless = _call(jesse, 'import', json={'slug': 'no-class'})
    assert (classless.status_code, classless.json()) == (400, {
        'status': 'error', 'message': 'No Python class definition found in strategy code. Cannot import strategy.'})

    existing = project / 'strategies' / CLASS_NAME
    existing.mkdir()
    (existing / '__init__.py').write_text('# local work\n')
    collision = _call(jesse, 'import')
    assert (collision.status_code, collision.json()) == (409, {
        'status': 'error', 'message': f'Strategy "{CLASS_NAME}" already exists.', 'name': CLASS_NAME})
    assert (existing / '__init__.py').read_text() == '# local work\n'


@pytest.mark.parametrize('route', ROUTES)
def test_a_slow_jesse_trade_does_not_hold_up_other_requests(jesse, jesse_trade, route):
    """
    While one route waits on jesse.trade, an async route on the same app answers at once.
    With an `async def` handler the whole event loop waited out the held request.
    """
    jesse_trade.hold.add(ROUTES[route]['upstream'][1])
    result = {}
    held = threading.Thread(target=lambda: result.setdefault('response', _call(jesse, route)))
    held.start()
    try:
        jesse_trade.wait_for(1)
        started = time.monotonic()
        probe = requests.get(f'{jesse.url}/probe', timeout=WAIT_SECONDS)
        probe_seconds = time.monotonic() - started
        other = jesse.request('GET', '/strategy/all')
        other_seconds = time.monotonic() - started
        still_waiting = held.is_alive()
    finally:
        jesse_trade.release.set()
        held.join(WAIT_SECONDS)

    assert probe.json() == {'ok': True} and probe_seconds < RESPONSIVE_SECONDS
    assert other.status_code == 200 and other_seconds < RESPONSIVE_SECONDS
    assert still_waiting is True
    # The held request then completes with its normal answer.
    assert (result['response'].status_code, result['response'].json()) == (200, _expected_success(route))


def _slow_strategy_folder_creation(monkeypatch) -> None:
    """
    Widen the gap between import_strategy's "folder missing" check and its makedirs, so two
    imports that are not kept one at a time would both pass the check.
    """
    real_makedirs = os.makedirs

    def slow_makedirs(path, *args, **kwargs):
        # 0.4 s is far longer than the time between the two requests reaching import_strategy
        # once jesse.trade releases both downloads together.
        if str(path).startswith('strategies/'):
            time.sleep(0.4)
        return real_makedirs(path, *args, **kwargs)

    monkeypatch.setattr(strategy_handler.os, 'makedirs', slow_makedirs)


def _import_both(jesse: _Jesse, jesse_trade: _JesseTrade, slugs: list) -> dict:
    """Start imports of `slugs` together; release jesse.trade once all downloads are in flight."""
    jesse_trade.hold.update(f'/strategies/{slug}' for slug in slugs)
    results = {}
    threads = [threading.Thread(target=lambda s=slug: results.setdefault(s, _call(jesse, 'import', json={'slug': s})))
               for slug in slugs]
    for thread in threads:
        thread.start()
    # Both downloads run at the same time: the lock covers only the local write.
    jesse_trade.wait_for(len(slugs))
    jesse_trade.release.set()
    for thread in threads:
        thread.join(WAIT_SECONDS)
    return results


def test_overlapping_imports_of_one_class_name_cannot_both_succeed(jesse, jesse_trade, project, monkeypatch):
    """Two catalog entries whose code defines the same class: one import wins, the other gets 409."""
    jesse_trade.codes = {'first': _code('SharedName', 'first'), 'second': _code('SharedName', 'second')}
    _slow_strategy_folder_creation(monkeypatch)

    results = _import_both(jesse, jesse_trade, ['first', 'second'])

    statuses = {slug: response.status_code for slug, response in results.items()}
    assert sorted(statuses.values()) == [200, 409], statuses
    [winner] = [slug for slug, status in statuses.items() if status == 200]
    [loser] = [slug for slug, status in statuses.items() if status == 409]
    assert results[loser].json() == {'status': 'error', 'message': 'Strategy "SharedName" already exists.', 'name': 'SharedName'}
    assert (project / 'strategies' / 'SharedName' / '__init__.py').read_text() == _code('SharedName', winner)


def test_overlapping_imports_of_different_names_both_succeed(jesse, jesse_trade, project, monkeypatch):
    jesse_trade.codes = {'alpha': _code('AlphaImported'), 'beta': _code('BetaImported')}
    _slow_strategy_folder_creation(monkeypatch)

    results = _import_both(jesse, jesse_trade, ['alpha', 'beta'])

    assert {slug: response.status_code for slug, response in results.items()} == {'alpha': 200, 'beta': 200}
    assert (project / 'strategies' / 'AlphaImported' / '__init__.py').read_text() == _code('AlphaImported')
    assert (project / 'strategies' / 'BetaImported' / '__init__.py').read_text() == _code('BetaImported')
