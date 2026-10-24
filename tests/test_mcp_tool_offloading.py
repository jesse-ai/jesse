"""
Every MCP tool except three pure in-memory ones is async and runs its blocking work (Jesse
API calls, local file reads, usage metering) in a worker thread (jesse/mcp/tools/offload.py);
a few Jesse routes that are unsafe to overlap are serialized (services/locks.py).

The real MCP worker (FastMCP, Streamable HTTP, token auth) runs under uvicorn on an
ephemeral loopback port, driven by the MCP SDK client or by raw JSON-RPC where a test must
send a cancellation or drop a connection. The worker's HTTP calls to the Jesse API go
through `_Gate` to the real Jesse routers in-process, inside a disposable project and a
throwaway SQLite database; `_Gate` can hold selected routes to stand in for a slow copy,
snapshot, write, or job start. Routes that would start real runs are replaced by recording
stand-ins, and the licensing backend's usage check by `_Meter`.
"""
import asyncio
import contextlib
import inspect
import json
import logging
import uuid

import os
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import anyio
import anyio.to_thread
import httpx
import peewee
import pytest
import requests
import uvicorn
from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.fastmcp.tools.base import Tool
from mcp.types import LATEST_PROTOCOL_VERSION, ImageContent, TextContent

import jesse.mcp.server as mcp_server
import jesse.mcp.tools.services.config as config_service
import jesse.mcp.tools.services.project_files as project_files_service
import jesse.mcp.usage_limits as usage_limits
from jesse.controllers import (
    analysis_controller,
    config_controller,
    data_provider_credentials_controller,
    exchange_controller,
    project_files_controller,
    research_scripts_controller,
    strategy_controller,
)
from jesse.mcp.auth import dashboard_token
from tests.conftest import process_exited
from jesse.mcp.tools import offload
from jesse.mcp.tools.services import (
    create_strategy_service,
    get_analysis_artifact_service,
    get_backtest_config_service,
    get_config_service,
    get_exchange_api_key_requirements_service,
    get_exchange_api_keys_service,
    get_indicator_details_service,
    list_indicators_service,
    list_project_files_service,
    read_project_file_service,
    read_strategy_service,
    save_strategy_report_service,
    write_project_file_service,
    write_strategy_service,
)
from jesse.mcp.tools.services.session_config import resolve_session_run_config
from jesse.models.DataProviderCredentials import DataProviderCredentials
from jesse.models.ExchangeApiKeys import ExchangeApiKeys
from jesse.models.Option import Option
from jesse.modes import data_provider
from jesse.services import analysis_jobs, auth, research_jobs

PASSWORD = 'offloading-test-password'
MCP_HEADERS = {'Authorization': f'Bearer {dashboard_token(PASSWORD)}', 'Accept': 'application/json, text/event-stream'}
STRATEGY_CODE = 'class MyStrategy:\n    pass\n'
# Generous upper bound for loopback operations; failures show up as timeouts, not hangs.
WAIT_SECONDS = 15
# How long a gated API call may be held before the gate gives up, so a failing test can
# never leave a worker thread blocked forever.
GATE_SECONDS = 60

PROJECT_AND_JOB_TOOLS = {
    'list_project_files', 'read_project_file', 'write_project_file', 'create_project_directory',
    'move_project_path', 'copy_project_path', 'delete_project_path',
    'run_research_script', 'get_research_job_status', 'get_research_job_output', 'cancel_research_job',
    'get_session_results', 'get_live_sessions', 'get_live_trades', 'get_live_orders',
    'run_analysis', 'get_analysis_job', 'get_analysis_artifact', 'cancel_analysis_job', 'delete_analysis_job',
}
# The only synchronous tools: they inspect loaded code and in-memory tables, nothing else.
SYNC_TOOLS = {'list_indicators', 'get_indicator_details', 'get_exchange_api_key_requirements'}
# Every tool the worker registers, including the 7 live/paper session tools, the 2 live/paper
# trade and order history tools, and the candle export and purge tools; the live tools are
# registered even without the plugin and answer live_plugin_unavailable then.
REGISTERED_TOOL_COUNT = 103
# Tools metered by usage_limits.gated, with the route prefix whose /sessions/{id} they read first.
GATED_RUN_TOOLS = {
    'run_backtest': 'backtest',
    'run_significance_test': 'significance-test',
    'run_monte_carlo': 'monte-carlo',
    'run_optimization': 'optimization',
}
RUN_SESSION_ID = '5a3f0c6e-2d7b-4f1e-9a0c-6b8e1d2f3a4b'
# Fake credential values with distinctive ends, so a masked fragment would be caught too.
FAKE_API_KEY = 'QZXAoffload-key-sentinel-0001VWKA'
FAKE_API_SECRET = 'QZXBoffload-secret-sentinel-0002VWKB'
FAKE_PASSPHRASE = 'QZXCoffload-passphrase-sentinel-VWKC'
FAKE_SECRETS = (FAKE_API_KEY, FAKE_API_SECRET, FAKE_PASSPHRASE)

CHART_CODE = '''
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(4, 2))
ax.plot([1, 3, 2])
fig.savefig("output/line.png", dpi=60)
print("saved")
'''


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

class _Gate:
    """
    Replaces `requests.post` and `requests.request` for the MCP services: forwards each call
    to the real Jesse routers, holding calls to `hold` routes until `release` is set, and
    raising the exception mapped in `fail` instead of forwarding. Records which threads made
    calls, which routes were started and finished, and how many held calls were in progress
    at once.
    """

    def __init__(self, api: TestClient) -> None:
        self.api = api
        self.hold: set = set()
        self.fail: dict = {}
        self.release = threading.Event()
        self.lock = threading.Lock()
        self.inside = 0
        self.max_inside = 0
        self.started: list = []
        self.finished: list = []
        self.thread_ids: set = set()

    def post(self, url, json=None, headers=None, timeout=None):
        return self.request('POST', url, json=json, headers=headers, timeout=timeout)

    def request(self, method, url, params=None, json=None, headers=None, timeout=None):
        route = url.removeprefix('http://jesse.test')
        with self.lock:
            self.thread_ids.add(threading.get_ident())
            self.started.append(route)
            held = route in self.hold
            if held:
                self.inside += 1
                self.max_inside = max(self.max_inside, self.inside)
        try:
            if held and not self.release.wait(GATE_SECONDS):
                raise AssertionError(f'{route} was never released')
            if route in self.fail:
                raise self.fail[route]
            response = self.api.request(method, route, params=params, json=json, headers=headers)
        finally:
            with self.lock:
                if held:
                    self.inside -= 1
                self.finished.append(route)
        return response

    def done(self, route: str) -> bool:
        with self.lock:
            return route in self.finished

    def count(self, route: str) -> int:
        with self.lock:
            return self.started.count(route)


class _Meter:
    """
    Stands in for the licensing backend's usage check (usage_limits._remote_usage_decision,
    one POST to api2 per metered run). Counts the checks, can hold them until `release` is
    set, and answers allowed (or not) with a fixed reset time so results are comparable.
    """

    def __init__(self) -> None:
        self.hold = False
        self.allowed = True
        self.entered = threading.Event()
        self.release = threading.Event()
        self.lock = threading.Lock()
        self.calls = 0

    def result(self) -> usage_limits.ConsumeResult:
        return usage_limits.ConsumeResult(
            allowed=self.allowed, used=3 if self.allowed else 100, limit=100,
            reset_at='2026-09-29T00:00:00+00:00', is_guest=False,
        )

    def __call__(self, feature: str) -> usage_limits.ConsumeResult:
        assert feature == 'mcp'
        with self.lock:
            self.calls += 1
        self.entered.set()
        if self.hold and not self.release.wait(GATE_SECONDS):
            raise AssertionError('the usage check was never released')
        return self.result()


class _ThreadedServer:
    """Serve an ASGI app with uvicorn on an ephemeral loopback port in a daemon thread."""

    def __init__(self, app, graceful_shutdown_seconds: float = 2) -> None:
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind(('127.0.0.1', 0))
        self.url = f'http://127.0.0.1:{self._socket.getsockname()[1]}/mcp'
        config = uvicorn.Config(
            app, lifespan='on', log_level='warning', access_log=False,
            timeout_graceful_shutdown=graceful_shutdown_seconds,
        )
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, kwargs={'sockets': [self._socket]}, daemon=True)

    def __enter__(self) -> '_ThreadedServer':
        self.thread.start()
        deadline = time.monotonic() + WAIT_SECONDS
        while not self.server.started:
            if not self.thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError('test server failed to start')
            time.sleep(0.01)
        return self

    def __exit__(self, *exc_info) -> None:
        self.server.should_exit = True
        self.thread.join(WAIT_SECONDS)
        self._socket.close()


class _RawSession:
    """Plain JSON-RPC over Streamable HTTP, for cancellations and dropped connections."""

    def __init__(self, http: httpx.AsyncClient, url: str) -> None:
        self.http = http
        self.url = url
        self.session_id = ''

    def _headers(self) -> dict:
        return {**MCP_HEADERS, 'mcp-session-id': self.session_id, 'mcp-protocol-version': LATEST_PROTOCOL_VERSION}

    async def open(self) -> None:
        response = await self.http.post(self.url, headers=MCP_HEADERS, json={
            'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
            'params': {'protocolVersion': LATEST_PROTOCOL_VERSION, 'capabilities': {},
                       'clientInfo': {'name': 'jesse-tests', 'version': '1.0'}},
        })
        assert response.status_code == 200, response.text
        self.session_id = response.headers['mcp-session-id']
        await self.notify('notifications/initialized')

    async def notify(self, method: str, params: Optional[dict] = None) -> None:
        message = {'jsonrpc': '2.0', 'method': method, **({'params': params} if params else {})}
        response = await self.http.post(self.url, headers=self._headers(), json=message)
        assert response.status_code == 202, response.text

    async def call(self, request_id: int, name: str, arguments: dict) -> dict:
        response = await self.http.post(self.url, headers=self._headers(), json={
            'jsonrpc': '2.0', 'id': request_id, 'method': 'tools/call', 'params': {'name': name, 'arguments': arguments},
        })
        assert response.status_code == 200, response.text
        return response.json()

    async def list_tools(self, request_id: int) -> dict:
        response = await self.http.post(self.url, headers=self._headers(), json={
            'jsonrpc': '2.0', 'id': request_id, 'method': 'tools/list',
        })
        assert response.status_code == 200, response.text
        return response.json()

    async def cancel(self, request_id: int) -> None:
        await self.notify('notifications/cancelled', {'requestId': request_id, 'reason': 'test'})

    async def delete(self) -> int:
        return (await self.http.delete(self.url, headers=self._headers())).status_code


def _tool_payload(reply: dict) -> dict:
    """The dict a tool returned, from a raw JSON-RPC tools/call result."""
    assert 'result' in reply, reply
    return json.loads(reply['result']['content'][0]['text'])


async def _wait_for(condition: Callable[[], bool], seconds: float = WAIT_SECONDS) -> None:
    with anyio.fail_after(seconds):
        while not condition():
            await anyio.sleep(0.01)


def _log_messages(caplog) -> list:
    return [record.getMessage() for record in caplog.records if record.name == 'jesse.mcp.tools']


def _session_crashes(caplog) -> list:
    """The SDK's "Session ... crashed" errors: an exception that ended a whole MCP session."""
    return [record.getMessage() for record in caplog.records
            if record.name.startswith('mcp.') and 'crashed' in record.getMessage()]


@pytest.fixture
def project(tmp_path, monkeypatch) -> Path:
    root = tmp_path / 'project'
    (root / 'strategies' / 'MyStrategy').mkdir(parents=True)
    (root / 'strategies' / 'MyStrategy' / '__init__.py').write_text(STRATEGY_CODE, encoding='utf-8')
    (root / 'storage').mkdir()
    (root / 'research_scripts').mkdir()
    (root / 'research_scripts' / 'sleeper.py').write_text('import time\ntime.sleep(120)\n', encoding='utf-8')
    monkeypatch.chdir(root)
    # Short grace periods keep cancellation fast; production values are asserted in the research tests.
    monkeypatch.setattr(research_jobs, 'TERMINATE_GRACE_SECONDS', 1.0)
    monkeypatch.setattr(research_jobs, '_POLL_SECONDS', 0.05)
    yield root
    research_jobs.terminate_all_jobs()
    with research_jobs._jobs_lock:
        research_jobs._jobs.clear()
    analysis_jobs._preparing.clear()


def _run_routes(recorded: dict) -> APIRouter:
    """
    Stand-ins for the routes the metered run tools and draft tools call, which in Jesse
    would start real backtests, optimizations, and simulations. They record each request and
    answer like Jesse: a stored draft with a one-route form, and 202 for a started run.
    """
    router = APIRouter()
    form = {
        'exchange': 'Binance Perpetual Futures',
        'routes': [{'exchange': 'Binance Perpetual Futures', 'strategy': 'MyStrategy', 'symbol': 'BTC-USDT', 'timeframe': '4h'}],
        'data_routes': [], 'start_date': '2024-01-01', 'finish_date': '2024-02-01', 'n_simulations': 100,
    }

    @router.post('/significance-test/sessions/{session_id}')
    def significance_session(session_id: str):
        return {'session': {'id': session_id, 'state': {'form': dict(form), 'results': {}}}}

    @router.post('/significance-test')
    def start_significance_test(payload: dict):
        recorded['runs'].append(payload['id'])
        return JSONResponse({'message': 'Started'}, status_code=202)

    @router.post('/backtest/update-state')
    def update_backtest_state(payload: dict):
        recorded['states'].append(payload)
        return {'message': 'ok'}

    @router.post('/backtest/sessions/{session_id}/notes')
    def update_backtest_notes(session_id: str, payload: dict):
        recorded['notes'].append(payload)
        return {'message': 'ok'}

    return router


@pytest.fixture
def recorded() -> dict:
    return {'runs': [], 'states': [], 'notes': []}


@pytest.fixture
def api(tmp_path, monkeypatch, recorded) -> TestClient:
    """
    The real Jesse routers the tools under test call, over a throwaway SQLite file (a file,
    not ':memory:', because each thread's peewee connection would see its own empty
    in-memory database), plus the stand-ins from _run_routes.
    """
    monkeypatch.setitem(auth.ENV_VALUES, 'PASSWORD', PASSWORD)
    # SQLite keeps datetimes as text that peewee cannot parse back when they carry a zone.
    monkeypatch.setattr('jesse.helpers.now_to_datetime', lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    app = FastAPI()

    @app.exception_handler(auth.InvalidAuthError)
    async def invalid_auth_handler(_request, _exc):
        return auth.unauthorized_response()

    app.include_router(project_files_controller.router)
    app.include_router(research_scripts_controller.router)
    app.include_router(analysis_controller.router)
    app.include_router(strategy_controller.router)
    app.include_router(config_controller.router)
    app.include_router(exchange_controller.router)
    app.include_router(data_provider_credentials_controller.router)
    app.include_router(_run_routes(recorded))
    db = peewee.SqliteDatabase(str(tmp_path / 'offloading.db'))
    models = [Option, ExchangeApiKeys, DataProviderCredentials]
    with db.bind_ctx(models):
        db.create_tables(models)
        yield TestClient(app)
    db.close()


@pytest.fixture
def gate(api, monkeypatch) -> _Gate:
    forwarder = _Gate(api)
    monkeypatch.setattr(project_files_service.mcp_config, 'JESSE_API_URL', 'http://jesse.test')
    monkeypatch.setattr(project_files_service.mcp_config, 'JESSE_PASSWORD', PASSWORD)
    monkeypatch.setattr(requests, 'post', forwarder.post)
    monkeypatch.setattr(requests, 'request', forwarder.request)
    yield forwarder
    forwarder.release.set()


@pytest.fixture
def meter(monkeypatch) -> _Meter:
    fake = _Meter()
    monkeypatch.setattr(usage_limits, 'USAGE_METER_BACKEND', 'remote')
    monkeypatch.setattr(usage_limits, '_remote_usage_decision', fake)
    yield fake
    fake.release.set()


def _worker_app():
    return mcp_server.create_app(mcp_server.create_mcp_server(0), PASSWORD)


@pytest.fixture
def worker(project, gate):
    with _ThreadedServer(_worker_app()) as server:
        yield server
        # Let any held call finish so shutdown does not wait for the gate's own timeout.
        gate.release.set()


# ---------------------------------------------------------------------------
# Scope and schemas
# ---------------------------------------------------------------------------

def test_every_tool_is_async_except_the_three_pure_in_memory_ones():
    tools = mcp_server.create_mcp_server(0)._tool_manager.list_tools()
    sync_tools = {tool.name for tool in tools if not tool.is_async}

    assert sync_tools == SYNC_TOOLS
    assert len(tools) == REGISTERED_TOOL_COUNT
    assert PROJECT_AND_JOB_TOOLS | set(GATED_RUN_TOOLS) <= {tool.name for tool in tools}


def _sync_twin(tool: Tool) -> Callable:
    """A synchronous function with the tool's exact signature, annotations, and docstring."""
    def twin(*_args, **_kwargs):
        raise AssertionError('only used to derive a schema')

    setattr(twin, '__signature__', inspect.signature(tool.fn))  # read by inspect.signature()
    twin.__annotations__ = dict(tool.fn.__annotations__)
    twin.__doc__ = tool.fn.__doc__
    twin.__name__ = tool.fn.__name__
    return twin


def test_async_tools_advertise_the_same_schemas_as_synchronous_functions():
    """Input schema, output schema, description, and annotations are what a sync def would give."""
    server = mcp_server.create_mcp_server(0)
    advertised = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    checked = 0
    for tool in server._tool_manager.list_tools():
        if not tool.is_async:
            continue
        twin = Tool.from_function(_sync_twin(tool), name=tool.name)
        assert not twin.is_async
        assert tool.parameters == twin.parameters == advertised[tool.name].inputSchema, tool.name
        assert tool.fn_metadata.output_schema == twin.fn_metadata.output_schema, tool.name
        assert advertised[tool.name].outputSchema is None, tool.name
        assert tool.description == twin.description == advertised[tool.name].description, tool.name
        assert tool.annotations == twin.annotations and advertised[tool.name].annotations is None, tool.name
        assert tool.context_kwarg is None, tool.name
        checked += 1
    assert checked == REGISTERED_TOOL_COUNT - len(SYNC_TOOLS)


# ---------------------------------------------------------------------------
# run_blocking
# ---------------------------------------------------------------------------

def test_run_blocking_runs_the_call_in_a_worker_thread_and_returns_it_unchanged():
    result = {'status': 'success', 'nested': [1, 2]}
    seen = []

    def service(value, other):
        seen.append(threading.get_ident())
        return value if other == 'x' else None

    async def main():
        returned = await offload.run_blocking(service, result, 'x')
        return returned, threading.get_ident()

    returned, loop_thread = anyio.run(main)

    assert returned is result
    assert seen and seen[0] != loop_thread

    def failing():
        raise ValueError('boom')

    with pytest.raises(ValueError, match='boom'):
        anyio.run(offload.run_blocking, failing)


def test_run_blocking_never_starts_a_call_that_was_cancelled_first():
    calls = []

    async def main():
        with anyio.CancelScope() as scope:
            scope.cancel()
            await offload.run_blocking(calls.append, 'ran')
        return scope.cancelled_caught

    assert anyio.run(main) is True
    assert calls == []


def test_run_blocking_finishes_a_started_call_before_honoring_cancellation(caplog):
    caplog.set_level(logging.INFO, logger='jesse.mcp.tools')
    started, release = threading.Event(), threading.Event()
    finished = []

    def write_project_file_service(path):
        started.set()
        release.wait(WAIT_SECONDS)
        finished.append(path)
        return {'status': 'success', 'path': path}

    async def main():
        outcome = {}
        # Stands in for the SDK's per-request cancel scope around the tool call.
        request_scope = anyio.CancelScope()

        async def call():
            with request_scope:
                # The result is not returned: the SDK has already answered the request.
                outcome['result'] = await offload.run_blocking(write_project_file_service, 'strategies/X/a.py')
            outcome['cancelled_caught'] = request_scope.cancelled_caught
            outcome['returned_at'] = time.monotonic()

        async with anyio.create_task_group() as tg:
            tg.start_soon(call)
            await anyio.to_thread.run_sync(started.wait, WAIT_SECONDS)
            request_scope.cancel()
            cancelled_at = time.monotonic()
            await anyio.sleep(0.3)
            outcome['finished_before_release'] = bool(finished)
            outcome['returned_before_release'] = 'returned_at' in outcome
            outcome['released_at'] = time.monotonic()
            release.set()
        outcome['waited'] = outcome['returned_at'] - cancelled_at
        return outcome

    outcome = anyio.run(main)

    assert outcome['finished_before_release'] is False and outcome['returned_before_release'] is False
    assert finished == ['strategies/X/a.py']  # never abandoned: the call ran to completion
    assert 'result' not in outcome and outcome['cancelled_caught'] is True
    # Windows clock granularity can shorten the measured sleep; completion must follow the release event.
    assert outcome['returned_at'] >= outcome['released_at']
    assert outcome['waited'] < WAIT_SECONDS
    assert _log_messages(caplog) == [
        'write_project_file_service finished after its MCP request was cancelled or its session closed (status: success).'
    ]


def test_run_blocking_raises_the_cancellation_when_a_cancelled_call_fails(caplog):
    caplog.set_level(logging.INFO, logger='jesse.mcp.tools')
    started, release = threading.Event(), threading.Event()

    def copy_project_path_service():
        started.set()
        release.wait(WAIT_SECONDS)
        raise ConnectionError('Jesse went away')

    async def main():
        request_scope = anyio.CancelScope()
        caught = {}

        async def call():
            with request_scope:
                try:
                    await offload.run_blocking(copy_project_path_service)
                except ConnectionError:
                    caught['error'] = True
            caught['cancelled'] = request_scope.cancelled_caught

        async with anyio.create_task_group() as tg:
            tg.start_soon(call)
            await anyio.to_thread.run_sync(started.wait, WAIT_SECONDS)
            request_scope.cancel()
            await anyio.sleep(0.1)
            release.set()
        return caught

    assert anyio.run(main) == {'cancelled': True}
    assert _log_messages(caplog) == [
        'copy_project_path_service finished after its MCP request was cancelled or its session closed '
        '(raised ConnectionError).'
    ]


def test_run_blocking_is_bounded_by_the_default_thread_limiter():
    order = []
    first_started, release_first = threading.Event(), threading.Event()

    def first():
        order.append('first started')
        first_started.set()
        release_first.wait(WAIT_SECONDS)
        order.append('first finished')

    def second():
        order.append('second started')

    async def main():
        limiter = anyio.to_thread.current_default_thread_limiter()
        limiter.total_tokens = 1
        async with anyio.create_task_group() as tg:
            tg.start_soon(offload.run_blocking, first)
            while not first_started.is_set():
                await anyio.sleep(0.01)
            tg.start_soon(offload.run_blocking, second)
            await anyio.sleep(0.3)
            assert order == ['first started']
            assert limiter.borrowed_tokens == 1 and limiter.statistics().tasks_waiting == 1
            release_first.set()

    anyio.run(main)

    assert order == ['first started', 'first finished', 'second started']


def test_run_blocking_does_not_log_normal_calls(caplog):
    caplog.set_level(logging.INFO, logger='jesse.mcp.tools')
    assert anyio.run(offload.run_blocking, dict) == {}
    assert _log_messages(caplog) == []


def test_run_blocking_passes_keyword_arguments_and_logs_only_the_service_name_and_status(caplog):
    caplog.set_level(logging.INFO, logger='jesse.mcp.tools')
    started, release = threading.Event(), threading.Event()

    def store_exchange_api_key_service(exchange, name=None, api_key=None):
        started.set()
        release.wait(WAIT_SECONDS)
        return {'status': 'error', 'error_type': 'name_taken', 'exchange': exchange, 'name': name, 'echo': api_key}

    assert anyio.run(lambda: offload.run_blocking(lambda a, b=0: (a, b), 1, b=2)) == (1, 2)

    async def main():
        request_scope = anyio.CancelScope()

        async def call():
            with request_scope:
                await offload.run_blocking(store_exchange_api_key_service, 'KuCoin Spot', name='Main', api_key=FAKE_API_KEY)

        async with anyio.create_task_group() as tg:
            tg.start_soon(call)
            await anyio.to_thread.run_sync(started.wait, WAIT_SECONDS)
            request_scope.cancel()
            await anyio.sleep(0.1)
            release.set()
        return request_scope.cancelled_caught

    assert anyio.run(main) is True
    assert _log_messages(caplog) == [
        'store_exchange_api_key_service finished after its MCP request was cancelled or its session closed '
        '(status: error, error_type: name_taken).'
    ]
    # Neither the arguments nor the result reach the log.
    assert FAKE_API_KEY not in caplog.text and 'KuCoin' not in caplog.text and 'Main' not in caplog.text


def _raw_tools() -> dict:
    """The registered tool functions themselves, as FastMCP calls them."""
    registered = {}

    class Registrar:
        def tool(self):
            def decorator(func):
                registered[func.__name__] = func
                return func
            return decorator

        def resource(self, _uri):
            return lambda func: func

    from jesse.mcp.tools import register_tools
    register_tools(Registrar())
    return registered


@pytest.mark.parametrize('tool', sorted(GATED_RUN_TOOLS))
def test_a_metered_run_cancelled_before_its_thread_starts_is_neither_metered_nor_sent(gate, meter, tool):
    run = _raw_tools()[tool]

    async def main():
        with anyio.CancelScope() as scope:
            scope.cancel()
            await run(RUN_SESSION_ID)
        return scope.cancelled_caught

    assert anyio.run(main) is True
    assert meter.calls == 0 and gate.started == []


# ---------------------------------------------------------------------------
# Real MCP worker
# ---------------------------------------------------------------------------

async def _sdk_session(url: str, scenario):
    async with httpx.AsyncClient(headers=MCP_HEADERS, trust_env=False, timeout=WAIT_SECONDS) as http_client:
        async with streamable_http_client(url, http_client=http_client) as (read, write, _session_id):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await scenario(session)


def test_slow_tool_calls_run_concurrently_while_other_requests_are_answered(project, gate, worker):
    (project / 'research_scripts' / 'data.bin').write_bytes(b'\x00model' * 1000)
    gate.hold = {'/project-files/copy', '/project-files/write'}

    async def scenario(session: ClientSession):
        results = {}

        async def call(key: str, name: str, arguments: dict) -> None:
            results[key] = await session.call_tool(name, arguments)

        async with anyio.create_task_group() as tg:
            tg.start_soon(call, 'copy', 'copy_project_path',
                          {'source': 'research_scripts/data.bin', 'destination': 'strategies/MyStrategy/model.pkl'})
            tg.start_soon(call, 'write', 'write_project_file',
                          {'path': 'strategies/NewStrategy/__init__.py', 'content': 'class NewStrategy:\n    pass\n'})
            # Both slow calls are inside their API request at the same time...
            await _wait_for(lambda: gate.inside == 2)
            # ...and the worker still answers everything else promptly.
            with anyio.fail_after(5):
                await session.send_ping()
                listed = await session.call_tool('list_project_files', {'path': 'strategies', 'recursive': True})
                status = await session.call_tool('get_research_job_status', {})
                tools = await session.list_tools()
            assert results == {}
            gate.release.set()
        return results, listed, status, tools

    results, listed, status, tools = asyncio.run(_sdk_session(worker.url, scenario))

    assert gate.max_inside == 2
    # Every API call ran in a worker thread, never on the MCP worker's event loop thread.
    assert worker.thread.ident not in gate.thread_ids
    listing = json.loads(listed.content[0].text)
    assert listing == {**list_project_files_service('strategies', True), 'entries': listing['entries']}
    assert [e['path'] for e in listing['entries']] == ['strategies/MyStrategy', 'strategies/MyStrategy/__init__.py']
    assert json.loads(status.content[0].text)['jobs'] == []
    assert PROJECT_AND_JOB_TOOLS <= {tool.name for tool in tools.tools}
    copied, written = json.loads(results['copy'].content[0].text), json.loads(results['write'].content[0].text)
    assert (copied['status'], copied['size_bytes'], written['status']) == ('success', 6000, 'success')
    assert (project / 'strategies' / 'MyStrategy' / 'model.pkl').read_bytes() == b'\x00model' * 1000
    assert (project / 'strategies' / 'NewStrategy' / '__init__.py').read_text() == 'class NewStrategy:\n    pass\n'


def test_results_errors_and_images_match_the_services(project, gate, worker):
    async def scenario(session: ClientSession):
        read = await session.call_tool('read_project_file', {'path': 'strategies/MyStrategy/__init__.py'})
        refused = await session.call_tool('write_project_file', {'path': 'strategies/MyStrategy/__init__.py', 'content': 'x'})
        invalid = await session.call_tool('delete_project_path', {'path': '../outside'})
        started = await session.call_tool('run_analysis', {'code': CHART_CODE})
        job_id = json.loads(started.content[0].text)['job']['id']
        for _ in range(WAIT_SECONDS * 20):
            job = json.loads((await session.call_tool('get_analysis_job', {'job_id': job_id})).content[0].text)
            if job['job']['status'] != 'running':
                break
            await anyio.sleep(0.05)
        image = await session.call_tool('get_analysis_artifact', {'job_id': job_id, 'path': 'line.png'})
        missing = await session.call_tool('get_analysis_artifact', {'job_id': job_id, 'path': '../job.json'})
        return read, refused, invalid, job, image, missing

    read, refused, invalid, job, image, missing = asyncio.run(_sdk_session(worker.url, scenario))

    assert json.loads(read.content[0].text) == read_project_file_service('strategies/MyStrategy/__init__.py')
    refused_payload = json.loads(refused.content[0].text)
    assert refused_payload == write_project_file_service('strategies/MyStrategy/__init__.py', 'x')
    assert refused_payload['error_type'] == 'already_exists' and not refused.isError
    assert json.loads(invalid.content[0].text)['error_type'] == 'invalid_path'
    assert (project / 'strategies' / 'MyStrategy' / '__init__.py').read_text() == STRATEGY_CODE

    assert job['job']['status'] == 'succeeded', job
    assert not image.isError
    assert [type(part) for part in image.content] == [TextContent, ImageContent]
    service_image = get_analysis_artifact_service(job['job']['id'], 'line.png')
    assert image.content[1].data == service_image['data_base64'] and image.content[1].mimeType == 'image/png'
    assert json.loads(image.content[0].text) == {k: v for k, v in service_image.items() if k != 'data_base64'}
    assert missing.isError and json.loads(missing.content[0].text)['error_type'] == 'invalid_path'


def test_a_cancelled_mutation_completes_is_logged_and_the_session_stays_usable(project, gate, worker, caplog):
    caplog.set_level(logging.INFO, logger='jesse.mcp.tools')
    gate.hold = {'/project-files/write'}
    target = project / 'strategies' / 'MyStrategy' / 'features.py'

    async def scenario():
        async with httpx.AsyncClient(timeout=WAIT_SECONDS, trust_env=False) as http:
            session = _RawSession(http, worker.url)
            await session.open()
            replies = {}

            async def call() -> None:
                replies['write'] = await session.call(7, 'write_project_file',
                                                      {'path': 'strategies/MyStrategy/features.py', 'content': 'X = 1\n'})

            async with anyio.create_task_group() as tg:
                tg.start_soon(call)
                await _wait_for(lambda: gate.inside == 1)
                await session.cancel(7)
                # The SDK answers the cancelled request at once, while the API call is still held.
                await _wait_for(lambda: 'write' in replies, 5)
                held_while_answered = gate.inside == 1 and not target.exists()
                gate.release.set()
            await _wait_for(lambda: gate.done('/project-files/write'))
            await _wait_for(lambda: bool(_log_messages(caplog)))
            read = await session.call(8, 'read_project_file', {'path': 'strategies/MyStrategy/features.py'})
            retry = await session.call(9, 'write_project_file', {'path': 'strategies/MyStrategy/features.py', 'content': 'X = 2\n'})
            return replies['write'], held_while_answered, read, retry

    reply, held_while_answered, read, retry = asyncio.run(scenario())

    assert reply['id'] == 7 and reply['error']['message'] == 'Request cancelled' and 'result' not in reply
    assert held_while_answered
    # The write was not abandoned half way: it completed on the Jesse host and was logged.
    assert target.read_text() == 'X = 1\n'
    assert _log_messages(caplog) == [
        'write_project_file_service finished after its MCP request was cancelled or its session closed (status: success).'
    ]
    assert _tool_payload(read)['content'] == 'X = 1\n'
    assert _session_crashes(caplog) == []
    # A blind retry refuses instead of replacing what the cancelled call wrote.
    assert _tool_payload(retry)['error_type'] == 'already_exists'
    assert target.read_text() == 'X = 1\n'


def test_a_cancelled_job_start_leaves_a_tracked_job_that_only_an_explicit_cancel_stops(project, gate, worker, caplog):
    caplog.set_level(logging.INFO, logger='jesse.mcp.tools')
    gate.hold = {'/research-scripts/run'}

    async def scenario():
        async with httpx.AsyncClient(timeout=WAIT_SECONDS, trust_env=False) as http:
            session = _RawSession(http, worker.url)
            await session.open()
            replies = {}

            async def call() -> None:
                replies['run'] = await session.call(7, 'run_research_script', {'path': 'research_scripts/sleeper.py'})

            async with anyio.create_task_group() as tg:
                tg.start_soon(call)
                await _wait_for(lambda: gate.inside == 1)
                await session.cancel(7)
                await _wait_for(lambda: 'run' in replies, 5)
                gate.release.set()
            await _wait_for(lambda: gate.done('/research-scripts/run'))
            listed = _tool_payload(await session.call(8, 'get_research_job_status', {}))
            await anyio.sleep(0.5)
            still = _tool_payload(await session.call(9, 'get_research_job_status', {'job_id': listed['jobs'][0]['id']}))
            cancelled = _tool_payload(await session.call(10, 'cancel_research_job', {'job_id': listed['jobs'][0]['id']}))
            return replies['run'], listed, still, cancelled

    reply, listed, still, cancelled = asyncio.run(scenario())

    assert reply['error']['message'] == 'Request cancelled'
    [job] = listed['jobs']
    assert (job['script'], job['status']) == ('research_scripts/sleeper.py', 'running')
    # Cancelling the MCP request did not stop the job; it keeps running until cancelled explicitly.
    assert still['job']['status'] == 'running'
    assert cancelled['job']['status'] == 'cancelled' and cancelled['cancel_requested'] is True
    assert process_exited(job['pid'])  # cancel waited for the job, so its process is already gone
    assert any('run_research_script_service finished after its MCP request was cancelled' in message
               for message in _log_messages(caplog))
    assert _session_crashes(caplog) == []


def test_a_dropped_connection_and_session_delete_do_not_deadlock(project, gate, worker, caplog):
    gate.hold = {'/project-files/copy'}
    destination = project / 'research_scripts' / 'backup'

    async def scenario():
        async with httpx.AsyncClient(timeout=WAIT_SECONDS, trust_env=False) as http:
            session = _RawSession(http, worker.url)
            await session.open()
            async with anyio.create_task_group() as tg:
                tg.start_soon(session.call, 7, 'copy_project_path',
                              {'source': 'strategies/MyStrategy', 'destination': 'research_scripts/backup'})
                await _wait_for(lambda: gate.inside == 1)
                # The client gives up: the HTTP request is abandoned and its connection closed.
                tg.cancel_scope.cancel()
            with anyio.fail_after(5):
                listed = _tool_payload(await session.call(8, 'list_project_files', {'path': 'strategies'}))
            gate.release.set()
            await _wait_for(lambda: gate.done('/project-files/copy'))
            with anyio.fail_after(5):
                deleted = await session.delete()
            after = await http.post(worker.url, headers=session._headers(),
                                    json={'jsonrpc': '2.0', 'id': 9, 'method': 'tools/list'})
            return listed, deleted, after.status_code

    listed, deleted, after_delete = asyncio.run(scenario())

    assert [e['path'] for e in listed['entries']] == ['strategies/MyStrategy']
    assert (destination / '__init__.py').read_text() == STRATEGY_CODE
    assert (deleted, after_delete) == (200, 404)
    assert _session_crashes(caplog) == []


def test_deleting_a_session_with_a_held_call_returns_at_once_and_the_call_still_completes(project, gate, worker, caplog):
    gate.hold = {'/project-files/write'}
    target = project / 'research_scripts' / 'late.py'

    async def scenario():
        async with httpx.AsyncClient(timeout=WAIT_SECONDS, trust_env=False) as http:
            first, second = _RawSession(http, worker.url), _RawSession(http, worker.url)
            await first.open()
            await second.open()
            outcome = {}

            async def call() -> None:
                outcome['reply'] = await _post_outcome(http, first, 7, 'write_project_file',
                                                       {'path': 'research_scripts/late.py', 'content': 'L\n'})

            async with anyio.create_task_group() as tg:
                tg.start_soon(call)
                await _wait_for(lambda: gate.inside == 1)
                with anyio.fail_after(5):
                    outcome['deleted'] = await first.delete()
                    await _wait_for(lambda: 'reply' in outcome)
                # Another session is unaffected while the call of the deleted one is still held.
                with anyio.fail_after(5):
                    outcome['other'] = _tool_payload(await second.call(8, 'list_project_files', {'path': 'research_scripts'}))
                outcome['held_after_delete'] = gate.inside == 1 and not target.exists()
                gate.release.set()
            await _wait_for(lambda: gate.done('/project-files/write'))
            return outcome

    outcome = asyncio.run(scenario())

    assert outcome['deleted'] == 200
    # The deleted session's pending request ends with the SDK's generic error, not a result.
    assert outcome['reply'][0] == 500 and 'result' not in outcome['reply'][1]
    assert outcome['held_after_delete'] is True
    assert _session_crashes(caplog) == []
    assert target.read_text() == 'L\n'
    assert outcome['other']['status'] == 'success'


async def _post_outcome(http: httpx.AsyncClient, session: _RawSession, request_id: int, name: str, arguments: dict):
    """The HTTP status and JSON-RPC body of a tools/call, or the transport error's name."""
    try:
        response = await http.post(session.url, headers=session._headers(), json={
            'jsonrpc': '2.0', 'id': request_id, 'method': 'tools/call', 'params': {'name': name, 'arguments': arguments},
        })
    except httpx.HTTPError as exc:
        return type(exc).__name__
    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, response.text


def test_shutdown_waits_for_a_started_call_and_then_exits(project, gate):
    gate.hold = {'/project-files/write'}
    target = project / 'research_scripts' / 'during_shutdown.py'
    server = _ThreadedServer(_worker_app(), graceful_shutdown_seconds=0.3)

    async def scenario():
        async with httpx.AsyncClient(timeout=WAIT_SECONDS, trust_env=False) as http:
            session = _RawSession(http, server.url)
            await session.open()
            outcome = {}

            async def call() -> None:
                outcome['reply'] = await _post_outcome(http, session, 7, 'write_project_file',
                                                       {'path': 'research_scripts/during_shutdown.py', 'content': 'S\n'})

            async with anyio.create_task_group() as tg:
                tg.start_soon(call)
                await _wait_for(lambda: gate.inside == 1)
                server.server.should_exit = True
                # Past uvicorn's graceful-shutdown timeout, the started call still holds shutdown.
                await anyio.sleep(1.0)
                outcome['alive_while_held'] = server.thread.is_alive()
                outcome['written_before_release'] = target.exists()
                gate.release.set()
                await anyio.to_thread.run_sync(server.thread.join, WAIT_SECONDS)
            return outcome

    with server:
        outcome = asyncio.run(scenario())

    # uvicorn ends the HTTP request at its graceful-shutdown timeout; the API call still finishes.
    assert outcome['reply'][0] == 500
    assert outcome['alive_while_held'] is True and outcome['written_before_release'] is False
    assert not server.thread.is_alive()
    assert target.read_text() == 'S\n'
    assert gate.inside == 0


# ---------------------------------------------------------------------------
# Strategy, configuration, credential, catalog, and metered run tools
# ---------------------------------------------------------------------------

NEW_STRATEGY_CODE = 'class MyStrategy:\n    VERSION = 2\n'
BASE_SETTINGS = {'backtest': {'warm_up_candles': 210, 'exchanges': {}}}


def _seed_config(settings: dict) -> None:
    Option.create(id=str(uuid.uuid4()), updated_at=0, type='config', json=json.dumps(settings))


def _stored_config() -> dict:
    return json.loads(Option.get(Option.type == 'config').json)


def _payload(result) -> dict:
    """The dict a tool returned, from an SDK CallToolResult."""
    assert not result.isError, result
    return json.loads(result.content[0].text)


def _discloses_nothing(text: str) -> bool:
    return not any(secret in text or secret[:4] in text or secret[-4:] in text for secret in FAKE_SECRETS)


def _worker_log(caplog) -> str:
    """
    Log text of the MCP worker side only. Excluded: the test's own SDK client, which logs
    every message it sends at DEBUG level (mcp.client), its httpx/httpcore connections, and
    peewee, whose DEBUG log of SQL parameters comes from the Jesse API routes this test serves
    in-process (a separate process in production).
    """
    return '\n'.join(record.getMessage() for record in caplog.records
                     if not record.name.startswith(('mcp.client', 'httpx', 'httpcore', 'peewee')))


def test_slow_older_tool_calls_run_concurrently_while_other_requests_are_answered(project, gate, meter, worker, recorded):
    _seed_config(BASE_SETTINGS)
    gate.hold = {'/strategy/save', '/strategy/save-report'}
    meter.hold = True

    async def scenario(session: ClientSession):
        results = {}

        async def call(key: str, name: str, arguments: dict) -> None:
            results[key] = await session.call_tool(name, arguments)

        async with anyio.create_task_group() as tg:
            tg.start_soon(call, 'write', 'write_strategy', {'name': 'MyStrategy', 'content': NEW_STRATEGY_CODE})
            tg.start_soon(call, 'report', 'save_strategy_report',
                          {'strategy_name': 'MyStrategy', 'filename': 'summary.md', 'content': '# Summary\n'})
            tg.start_soon(call, 'run', 'run_significance_test', {'session_id': RUN_SESSION_ID})
            # Two held API writes and one held usage check at the same time...
            await _wait_for(lambda: gate.inside == 2 and meter.entered.is_set())
            # ...while the worker answers everything else promptly, other older tools included.
            with anyio.fail_after(5):
                await session.send_ping()
                others = {
                    'read': await session.call_tool('read_strategy', {'name': 'MyStrategy'}),
                    'config': await session.call_tool('get_backtest_config', {}),
                    'keys': await session.call_tool('get_exchange_api_keys', {}),
                    'indicators': await session.call_tool('list_indicators', {}),
                    'files': await session.call_tool('list_project_files', {'path': 'strategies'}),
                    'tools': await session.list_tools(),
                }
            pending = sorted(results)
            gate.release.set()
            meter.release.set()
        return results, others, pending

    results, others, pending = asyncio.run(_sdk_session(worker.url, scenario))

    assert pending == [] and gate.max_inside == 2
    assert worker.thread.ident not in gate.thread_ids
    # Read while the write was still held: the old code.
    assert _payload(others['read'])['content'] == STRATEGY_CODE
    assert _payload(others['config'])['config']['warm_up_candles'] == 210
    assert _payload(others['keys'])['exchange_api_keys'] == []
    assert _payload(others['indicators'])['count'] > 100
    assert _payload(others['files'])['status'] == 'success'
    assert len(others['tools'].tools) == REGISTERED_TOOL_COUNT
    assert _payload(results['write'])['status'] == 'success'
    assert (project / 'strategies' / 'MyStrategy' / '__init__.py').read_text() == NEW_STRATEGY_CODE
    assert _payload(results['report'])['path'] == 'strategies/MyStrategy/reports/summary.md'
    assert _payload(results['run'])['status'] == 'started'
    assert meter.calls == 1 and recorded['runs'] == [RUN_SESSION_ID]


def _sync_tool_error(name: str, error: Exception) -> str:
    """The error text FastMCP gives for a synchronous tool raising `error`."""
    twin = FastMCP('sync-twin')

    def fail():
        raise error

    twin.add_tool(fail, name=name)
    with pytest.raises(ToolError) as info:
        asyncio.run(twin.call_tool(name, {}))
    return str(info.value)


def test_older_tool_results_and_errors_match_the_services(project, gate, worker):
    _seed_config(BASE_SETTINGS)
    report = {'strategy_name': 'MyStrategy', 'filename': 'a.md', 'content': '# A\n'}

    async def scenario(session: ClientSession):
        out = {}
        for key, name, arguments in [
            ('read', 'read_strategy', {'name': 'MyStrategy'}),
            ('missing', 'read_strategy', {'name': 'Missing'}),
            ('write_missing', 'write_strategy', {'name': 'Missing', 'content': 'x'}),
            ('exists', 'create_strategy', {'name': 'MyStrategy', 'content': 'x'}),
            ('report', 'save_strategy_report', report),
            ('report_again', 'save_strategy_report', report),
            ('bad_report', 'save_strategy_report', {**report, 'filename': '../a.md'}),
            ('config', 'get_config', {}),
            ('backtest_config', 'get_backtest_config', {}),
            ('keys', 'get_exchange_api_keys', {}),
            ('rsi', 'get_indicator_details', {'indicator_name': 'rsi'}),
            ('requirements', 'get_exchange_api_key_requirements', {'exchange': 'KuCoin Spot'}),
        ]:
            out[key] = await session.call_tool(name, arguments)
        gate.fail['/strategy/periods'] = RuntimeError('catalog backend down')
        out['browse'] = await session.call_tool('browse_strategy_catalog', {})
        return out

    out = asyncio.run(_sdk_session(worker.url, scenario))

    assert _payload(out['read']) == read_strategy_service('MyStrategy')
    assert _payload(out['missing']) == read_strategy_service('Missing')
    assert _payload(out['missing'])['error_type'] == 'strategy_not_found'
    assert _payload(out['write_missing']) == write_strategy_service('Missing', 'x')
    # create_strategy returns the creation error unchanged and never writes the content.
    assert _payload(out['exists']) == create_strategy_service('MyStrategy')
    assert _payload(out['exists'])['error_type'] == 'strategy_exists'
    assert (project / 'strategies' / 'MyStrategy' / '__init__.py').read_text() == STRATEGY_CODE
    saved = _payload(out['report'])
    assert (saved['status'], saved['overwritten'], saved['size_bytes']) == ('success', False, 4)
    assert _payload(out['report_again']) == save_strategy_report_service(**report)
    assert _payload(out['report_again'])['error_type'] == 'report_exists'
    assert _payload(out['bad_report']) == save_strategy_report_service(**{**report, 'filename': '../a.md'})
    assert _payload(out['config']) == get_config_service()
    assert _payload(out['backtest_config']) == get_backtest_config_service()
    assert _payload(out['keys']) == get_exchange_api_keys_service()
    assert _payload(out['rsi']) == json.loads(json.dumps(get_indicator_details_service('rsi'), default=str))
    assert _payload(out['requirements']) == get_exchange_api_key_requirements_service('KuCoin Spot')
    assert json.loads(out['keys'].content[0].text) == get_exchange_api_keys_service()
    # An exception from a service reaches the client exactly as it would from a sync tool.
    assert out['browse'].isError
    assert out['browse'].content[0].text == _sync_tool_error('browse_strategy_catalog', RuntimeError('catalog backend down'))


# FastMCP validates arguments with pydantic before a tool runs; its errors would quote the
# values. Missing arguments, unknown ones, and wrong types of each credential tool:
CREDENTIAL_ARGUMENT_CASES = [
    ('store_exchange_api_key', {'exchange': 'KuCoin Spot', 'api_key': FAKE_API_KEY, 'api_secret': FAKE_API_SECRET,
                                'additional_fields': {'api_passphrase': FAKE_PASSPHRASE}}),
    ('store_exchange_api_key', {'exchange': 'KuCoin Spot', 'name': 'Main', 'api_key': {'key': FAKE_API_KEY},
                                'api_secret': FAKE_API_SECRET, 'additional_fields': {'api_passphrase': FAKE_PASSPHRASE}}),
    ('store_exchange_api_key', {'exchange': 'KuCoin Spot', 'name': 'Main', 'api_key': FAKE_API_KEY,
                                'api_secret': FAKE_API_SECRET, 'additional_fields': FAKE_PASSPHRASE}),
    ('store_exchange_api_key', {'exchange': FAKE_API_SECRET, 'name': 'Main', 'api_key': FAKE_API_KEY,
                                'api_secret': [FAKE_API_SECRET]}),
    ('store_data_provider_credentials', {'key': FAKE_API_KEY}),
    ('store_data_provider_credentials', {'api_key': [FAKE_API_KEY]}),
    ('delete_exchange_api_key', {'exchange_api_key_id': FAKE_API_KEY}),
    ('delete_data_provider_credentials', {'provider_id': [FAKE_API_SECRET]}),
    ('validate_data_provider_credentials', {'provider_id': {'api_key': FAKE_API_KEY}}),
    ('get_exchange_api_key_requirements', {'exchange': [FAKE_API_SECRET]}),
]


def test_invalid_credential_arguments_are_never_echoed_through_the_sdk(project, gate, worker, caplog):
    caplog.set_level(logging.DEBUG)

    async def scenario(session: ClientSession):
        return [await session.call_tool(name, arguments) for name, arguments in CREDENTIAL_ARGUMENT_CASES]

    results = asyncio.run(_sdk_session(worker.url, scenario))

    for (name, _arguments), result in zip(CREDENTIAL_ARGUMENT_CASES, results):
        text = result.model_dump_json()
        assert not result.isError and 'Error executing tool' not in text, (name, text)
        assert _payload(result)['status'] == 'error', name
        assert _discloses_nothing(text), (name, text)
    # Every case was refused by the services' own validation, before any request to Jesse.
    assert gate.started == []
    assert 'CallToolRequest' in _worker_log(caplog) and _discloses_nothing(_worker_log(caplog))


@pytest.mark.parametrize('serialized', [True, False], ids=['with the lock', 'control without it'])
def test_config_reads_and_updates_of_this_worker_never_overlap(project, gate, worker, monkeypatch, serialized):
    """
    Jesse's /config/get saves back the config row it read. Held between that read and the
    save, a concurrent update_config waits for it under CONFIG_LOCK and persists. The control
    without the lock shows what the lock prevents: the update is written, then silently
    overwritten by the read's save.
    """
    _seed_config(BASE_SETTINGS)
    inside, release = threading.Event(), threading.Event()
    normalize = data_provider.normalize_settings_sections

    def held_normalize(data):
        # Runs inside Jesse's get_config after it read the row and before it saves it.
        inside.set()
        assert release.wait(GATE_SECONDS)
        return normalize(data)

    monkeypatch.setattr(data_provider, 'normalize_settings_sections', held_normalize)
    if not serialized:
        monkeypatch.setattr(config_service, 'CONFIG_LOCK', contextlib.nullcontext())

    async def scenario(session: ClientSession):
        results = {}

        async def call(key: str, name: str, arguments: dict) -> None:
            results[key] = await session.call_tool(name, arguments)

        async with anyio.create_task_group() as tg:
            tg.start_soon(call, 'get', 'get_config', {})
            await anyio.to_thread.run_sync(inside.wait, WAIT_SECONDS)
            tg.start_soon(call, 'update', 'update_config', {'config': json.dumps({'backtest': {'warm_up_candles': 555}})})
            if serialized:
                await anyio.sleep(0.5)
            else:
                await _wait_for(lambda: gate.done('/config/update'))
            reached_jesse = gate.count('/config/update')
            release.set()
        return results, reached_jesse

    results, reached_jesse = asyncio.run(_sdk_session(worker.url, scenario))

    assert _payload(results['get'])['config']['data']['backtest']['warm_up_candles'] == 210
    assert _payload(results['update'])['status'] == 'success'
    if serialized:
        assert reached_jesse == 0
        assert _stored_config()['backtest']['warm_up_candles'] == 555
    else:
        assert reached_jesse == 1
        assert _stored_config()['backtest']['warm_up_candles'] == 210


def test_overlapping_credential_changes_of_this_worker_run_one_at_a_time(project, gate, worker, caplog):
    caplog.set_level(logging.DEBUG)
    key = {'exchange': 'Binance Perpetual Futures', 'name': 'Main', 'api_key': FAKE_API_KEY, 'api_secret': FAKE_API_SECRET}

    async def overlapping(session: ClientSession, route: str, name: str, arguments: dict):
        gate.hold, gate.release = {route}, threading.Event()
        results = []

        async def call() -> None:
            results.append(await session.call_tool(name, arguments))

        async with anyio.create_task_group() as tg:
            tg.start_soon(call)
            tg.start_soon(call)
            await _wait_for(lambda: gate.inside == 1)
            await anyio.sleep(0.5)
            # The second call waits for the first instead of reaching Jesse alongside it.
            snapshot = (gate.inside, gate.count(route))
            gate.release.set()
        return snapshot, sorted((_payload(result) for result in results), key=lambda r: r['status'] != 'success')

    async def scenario(session: ClientSession):
        stores = await overlapping(session, '/exchange/api-keys/store', 'store_exchange_api_key', key)
        key_id = stores[1][0]['exchange_api_key']['id']
        deletes = await overlapping(session, '/exchange/api-keys/delete', 'delete_exchange_api_key', {'id': key_id})
        return stores, deletes

    (store_snapshot, stores), (delete_snapshot, deletes) = asyncio.run(_sdk_session(worker.url, scenario))

    assert store_snapshot == delete_snapshot == (1, 1)
    assert stores[0]['action'] == 'exchange_api_key_stored' and stores[1]['error_type'] == 'name_taken'
    assert deletes[0]['action'] == 'exchange_api_key_deleted' and deletes[1]['error_type'] == 'not_found'
    assert ExchangeApiKeys.select().count() == 0
    assert _discloses_nothing(json.dumps(stores + deletes)) and _discloses_nothing(_worker_log(caplog))


def test_overlapping_strategy_creation_of_this_worker_runs_one_at_a_time(project, gate, worker):
    gate.hold = {'/strategy/make'}
    code = {'a': 'class Dup:\n    SOURCE = "a"\n', 'b': 'class Dup:\n    SOURCE = "b"\n'}

    async def scenario(session: ClientSession):
        results = {}

        async def call(key: str) -> None:
            results[key] = _payload(await session.call_tool('create_strategy', {'name': 'Dup', 'content': code[key]}))

        async with anyio.create_task_group() as tg:
            tg.start_soon(call, 'a')
            tg.start_soon(call, 'b')
            await _wait_for(lambda: gate.inside == 1)
            await anyio.sleep(0.5)
            snapshot = (gate.inside, gate.count('/strategy/make'))
            gate.release.set()
        return snapshot, results

    snapshot, results = asyncio.run(_sdk_session(worker.url, scenario))

    assert snapshot == (1, 1)
    [winner] = [key for key, result in results.items() if result['status'] == 'success']
    [loser] = set(results) - {winner}
    assert results[winner]['action'] == 'strategy_created_and_populated'
    assert results[loser]['error_type'] == 'strategy_exists'
    assert (project / 'strategies' / 'Dup' / '__init__.py').read_text() == code[winner]


def test_a_cancelled_create_strategy_still_completes_both_steps(project, gate, worker, caplog):
    caplog.set_level(logging.INFO, logger='jesse.mcp.tools')
    gate.hold = {'/strategy/save'}
    target = project / 'strategies' / 'Cancelled' / '__init__.py'
    code = 'class Cancelled:\n    pass\n'

    async def scenario():
        async with httpx.AsyncClient(timeout=WAIT_SECONDS, trust_env=False) as http:
            session = _RawSession(http, worker.url)
            await session.open()
            replies = {}

            async def call() -> None:
                replies['create'] = await session.call(7, 'create_strategy', {'name': 'Cancelled', 'content': code})

            async with anyio.create_task_group() as tg:
                tg.start_soon(call)
                # The strategy was created from the template; filling in the code is held.
                await _wait_for(lambda: gate.inside == 1)
                template_only = target.exists() and target.read_text() != code
                await session.cancel(7)
                await _wait_for(lambda: 'create' in replies, 5)
                gate.release.set()
            await _wait_for(lambda: gate.done('/strategy/save'))
            await _wait_for(lambda: bool(_log_messages(caplog)))
            read = await session.call(8, 'read_strategy', {'name': 'Cancelled'})
            return replies['create'], template_only, read

    reply, template_only, read = asyncio.run(scenario())

    assert reply['error']['message'] == 'Request cancelled' and 'result' not in reply
    assert template_only is True
    # The cancellation did not stop the tool between its two requests.
    assert target.read_text() == code and _tool_payload(read)['content'] == code
    assert _log_messages(caplog) == [
        'create_strategy_and_populate finished after its MCP request was cancelled or its session closed (status: success).'
    ]
    assert _session_crashes(caplog) == []


def test_a_cancelled_metered_run_is_metered_and_started_once_and_the_session_survives(project, gate, meter, worker, recorded, caplog):
    caplog.set_level(logging.INFO, logger='jesse.mcp.tools')
    _seed_config(BASE_SETTINGS)
    meter.hold = True

    async def scenario():
        async with httpx.AsyncClient(timeout=WAIT_SECONDS, trust_env=False) as http:
            session = _RawSession(http, worker.url)
            await session.open()
            replies = {}

            async def call() -> None:
                replies['run'] = await session.call(7, 'run_significance_test', {'session_id': RUN_SESSION_ID})

            async with anyio.create_task_group() as tg:
                tg.start_soon(call)
                await anyio.to_thread.run_sync(meter.entered.wait, WAIT_SECONDS)
                await session.cancel(7)
                await _wait_for(lambda: 'run' in replies, 5)
                before_release = (meter.calls, list(gate.started))
                meter.release.set()
            await _wait_for(lambda: gate.done('/significance-test'))
            await _wait_for(lambda: bool(_log_messages(caplog)))
            listed = await session.list_tools(8)
            # Nothing retries the check or the run after the cancellation.
            await anyio.sleep(0.3)
            return replies['run'], before_release, listed

    reply, before_release, listed = asyncio.run(scenario())

    assert reply['error']['message'] == 'Request cancelled' and 'result' not in reply
    assert before_release == (1, [])
    assert meter.calls == 1 and recorded['runs'] == [RUN_SESSION_ID] and gate.count('/significance-test') == 1
    assert _log_messages(caplog) == [
        'run_significance_test_service finished after its MCP request was cancelled or its session closed (status: started).'
    ]
    assert len(listed['result']['tools']) == REGISTERED_TOOL_COUNT
    assert _session_crashes(caplog) == []


@pytest.mark.parametrize('tool', sorted(GATED_RUN_TOOLS))
def test_every_run_tool_is_metered_once_per_call(project, gate, meter, worker, recorded, tool):
    _seed_config(BASE_SETTINGS)
    session_route = f'/{GATED_RUN_TOOLS[tool]}/sessions/{RUN_SESSION_ID}'

    async def scenario(session: ClientSession):
        meter.allowed = False
        refused = await session.call_tool(tool, {'session_id': RUN_SESSION_ID})
        refused_calls = (meter.calls, list(gate.started))
        meter.allowed = True
        allowed = await session.call_tool(tool, {'session_id': RUN_SESSION_ID})
        return refused, refused_calls, allowed

    refused, refused_calls, allowed = asyncio.run(_sdk_session(worker.url, scenario))

    meter.allowed = False
    assert _payload(refused) == usage_limits._limit_reached_response(meter.result(), is_guest=False)
    assert refused_calls == (1, [])
    assert meter.calls == 2 and gate.count(session_route) == 1
    if tool == 'run_significance_test':
        assert _payload(allowed)['status'] == 'started' and recorded['runs'] == [RUN_SESSION_ID]
    else:
        # Only significance tests have a stand-in session here; the others report it missing.
        assert _payload(allowed) == {'status': 'error', 'message': f'{"Backtest session" if tool == "run_backtest" else "Session"} {RUN_SESSION_ID} not found'}
        assert recorded['runs'] == []


def test_concurrent_drafts_get_their_own_exchange_scoped_run_configs(project, gate, worker, recorded):
    exchanges = ['Binance Perpetual Futures', 'Bybit USDT Perpetual', 'Binance Spot']
    by_exchange = {
        exchange: {'warm_up_candles': 100 + index, 'exchange': {'balance': 1000 * (index + 1), 'fee': 0.001 * (index + 1)}}
        for index, exchange in enumerate(exchanges)
    }
    _seed_config({**BASE_SETTINGS, 'session_defaults': {'backtest': {'fallback': {'warm_up_candles': 300}, 'by_exchange': by_exchange}}})
    gate.hold = {'/backtest/update-state'}

    async def scenario(session: ClientSession):
        results = []

        async def call(exchange: str) -> None:
            route = [{'exchange': exchange, 'strategy': 'MyStrategy', 'symbol': 'BTC-USDT', 'timeframe': '4h'}]
            results.append((exchange, _payload(await session.call_tool(
                'create_backtest_draft', {'exchange': exchange, 'routes': json.dumps(route)}))))

        async with anyio.create_task_group() as tg:
            for exchange in exchanges * 2:
                tg.start_soon(call, exchange)
            # All six drafts are inside their state write at once.
            await _wait_for(lambda: gate.inside == 6)
            gate.release.set()
        return results

    results = asyncio.run(_sdk_session(worker.url, scenario))

    settings = get_config_service()['config']['data']
    assert len({result['backtest_id'] for _exchange, result in results}) == 6
    stored_states = {state['id']: state['state'] for state in recorded['states']}
    for exchange, result in results:
        config = result['draft_state']['form']['config']
        assert config == resolve_session_run_config(settings, 'backtest', exchange), exchange
        assert config['warm_up_candles'] == by_exchange[exchange]['warm_up_candles']
        assert config['exchange']['balance'] == by_exchange[exchange]['exchange']['balance']
        assert stored_states[result['backtest_id']] == result['draft_state']
        # Strategy code snapshots are read relative to the project root from worker threads.
        assert result['notes']['strategy_codes_captured'] == 1
    assert sorted(json.dumps(note['strategy_codes']) for note in recorded['notes']) == sorted(
        json.dumps({f'{exchange}-BTC-USDT': STRATEGY_CODE}) for exchange, _result in results)
