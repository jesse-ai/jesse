"""
End-to-end proof of session results and temporary analysis on a disposable Jesse instance.

Starts `jesse run` from a throwaway project with its own env file, a guarded test schema
(`mcp_analysis_e2e_test`, dropped and recreated at startup exactly like the dashboard E2E
stack), its own ports, and its own Redis DB. Real records are written into that schema with
Jesse's own model functions, then an MCP SDK client connects through the dashboard's
authenticated /mcp route and exercises the tools: results of every session type, a real
matplotlib analysis over snapshots, the chart as MCP image content, and earlier tools,
including a metered run whose usage check waits on a local stand-in for the licensing backend,
and the strategy catalog and license routes against a local stand-in for jesse.trade.
`jesse run` skips MCP in test mode, so each instance is started through a small entry point
that calls the real run_mcp_server inside the server process, just before the dashboard is
served, as a normal `jesse run` does; the worker gets its OS-assigned port the real way.

Nothing here reads a real .env, key, or wallet file, starts a backtest or live session, or
contacts an exchange; the live session is seeded rows only, with fake key values.

Opt-in because it needs local PostgreSQL and Redis:
    JESSE_MCP_INTEGRATION=1 pytest tests/test_mcp_session_analysis_integration.py
The database settings default to the dashboard E2E fixture's local test credentials and can
be overridden with JESSE_MCP_INTEGRATION_POSTGRES_{HOST,PORT,NAME,USERNAME,PASSWORD}.
"""
import asyncio
import base64
import io
import json
import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

pytestmark = pytest.mark.skipif(
    os.environ.get('JESSE_MCP_INTEGRATION') != '1',
    reason='Set JESSE_MCP_INTEGRATION=1 to run against a disposable Jesse instance (needs PostgreSQL and Redis).',
)

JESSE_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 'mcp_analysis_e2e_test'
STARTUP_SECONDS = 90
FAKE_API_KEY = 'E2E-FAKE-API-KEY-0123456789'
FAKE_API_SECRET = 'E2E-FAKE-API-SECRET-9876543210'
FAKE_PASSPHRASE = 'E2E-FAKE-PASSPHRASE-555'
# Every registered MCP tool, including the live/paper session and history tools and candle export/purge.
REGISTERED_TOOL_COUNT = 101

# `jesse run` with the MCP worker started by the real manager (see the module docstring).
RUN_WITH_MCP = r'''
import uvicorn
from jesse import cli
from jesse.mcp.manager import run_mcp_server

serve_dashboard = uvicorn.run


def serve_with_mcp(app, **kwargs):
    host, port = kwargs['host'], kwargs['port']
    run_mcp_server(host, port, f'http://{host}:{port}')
    serve_dashboard(app, **kwargs)


uvicorn.run = serve_with_mcp
cli()
'''
WORKER_PORT_LOG = re.compile(r'MCP worker listening on internal loopback port (\d+)')

# Runs inside the disposable project with its env file; writes real rows through Jesse's
# model and repository functions and prints the created IDs.
SEED_SCRIPT = r'''
import json, os, uuid
import jesse.helpers as jh
from jesse.models.BacktestSession import BacktestSession
from jesse.models.OptimizationSession import store_optimization_session, update_optimization_session_trials, update_optimization_session_status, OptimizationSession
from jesse.models.MonteCarloSession import (store_monte_carlo_session, store_candles_session, update_candles_session_progress,
    update_candles_session_status, update_monte_carlo_session_status)
from jesse.models.SignificanceTestSession import (store_significance_test_session, update_significance_test_session_results,
    update_significance_test_session_status)
from jesse.models.ExchangeApiKeys import ExchangeApiKeys
from jesse.models.ClosedTrade import ClosedTrade
from jesse.models.Order import Order
from jesse.models.LiveEquitySnapshot import LiveEquitySnapshot
from jesse.models.Log import store_log_into_db
from jesse.repositories import live_session_repository
from jesse.services.db import database
import datetime

ids = {k: str(uuid.uuid4()) for k in ('backtest_a', 'backtest_b', 'backtest_running', 'optimization', 'monte_carlo',
                                      'significance', 'live', 'key')}
form = {'exchange': 'Binance Perpetual Futures', 'routes': [{'strategy': 'Demo', 'symbol': 'BTC-USDT', 'timeframe': '4h'}],
        'data_routes': [], 'start_date': '2025-01-01', 'finish_date': '2025-07-01'}
DAY = 86400

def curve(name, points, slope):
    return {'name': name, 'color': '#818CF8', 'data': [{'time': 1735689600 + d * DAY, 'value': 10000 + d * slope, 'color': '#818CF8'} for d in range(points)]}

def backtest(session_id, slope, trades):
    metrics = {'total': trades, 'net_profit_percentage': slope * 2.0, 'max_drawdown': -3.5 * slope, 'sharpe_ratio': 0.8 * slope,
               'win_rate': 0.55, 'serenity_index': float('nan')}
    BacktestSession.create(
        id=session_id, status='finished', metrics=json.dumps(metrics),
        equity_curve=json.dumps([curve('Portfolio', 181, slope), curve('BTC-USDT', 181, 1)]),
        trades=json.dumps([{'id': f'{session_id[:4]}-{i}', 'symbol': 'BTC-USDT', 'type': 'long', 'entry_price': 100 + i,
                            'exit_price': 101 + i, 'qty': 1, 'opened_at': 1735689600000 + i * 3600000,
                            'closed_at': 1735693200000 + i * 3600000, 'PNL': i * slope, 'PNL_percentage': i / 10, 'orders': []}
                           for i in range(trades)]),
        hyperparameters=json.dumps([['fast', 10 * slope]]), state=json.dumps({'form': form}), title=f'E2E backtest {slope}',
        description='seeded', execution_duration=1.5, created_at=jh.now_to_timestamp(True), updated_at=jh.now_to_timestamp(True))

backtest(ids['backtest_a'], 1, 40)
backtest(ids['backtest_b'], 3, 25)
BacktestSession.create(id=ids['backtest_running'], status='running', state=json.dumps({'form': form}),
                       created_at=jh.now_to_timestamp(True), updated_at=jh.now_to_timestamp(True))
os.makedirs('storage/logs/backtest-mode', exist_ok=True)
with open(f'storage/logs/backtest-mode/{ids["backtest_a"]}.txt', 'w') as f:
    f.write(''.join(f'[2025-01-01] ==> log line {i}\n' for i in range(300)))

store_optimization_session(ids['optimization'], 'running')
trial_metrics = lambda r: {'net_profit_percentage': 20.0 - r, 'max_drawdown': -5.0, 'sharpe_ratio': 2.0 - r / 10, 'win_rate': 0.5, 'total': 30}
update_optimization_session_trials(ids['optimization'], 60, [
    {'trial': 10 + r, 'params': {'fast': r}, 'fitness': 1 / (r + 1), 'dna': f'd{r}', 'training_metrics': trial_metrics(r),
     'testing_metrics': trial_metrics(r)} for r in range(12)], 60)
OptimizationSession.update(state=json.dumps({'form': {**form, 'objective_function': 'sharpe'}})).where(
    OptimizationSession.id == ids['optimization']).execute()
update_optimization_session_status(ids['optimization'], 'finished')

store_monte_carlo_session(ids['monte_carlo'], 'running', {'form': form})
child = store_candles_session(ids['monte_carlo'], 30, 'gaussian_noise', {'batch_size': 5})
scenario = lambda i: {'scenario_index': i, 'metrics': {'sharpe_ratio': 0.5 + i / 30, 'net_profit_percentage': i},
                      'equity_curve': [curve('Portfolio', 120, 1 + i / 10)]}
ca = {'metrics': {m: {'original': 1.1, 'percentiles': {'5th': 0.2, '50th': 0.9, '95th': 1.5}}
                  for m in ('sharpe_ratio', 'net_profit_percentage', 'max_drawdown')}, 'summary': {}}
update_candles_session_progress(child, 30, {'original': scenario(0), 'scenarios': [scenario(i + 1) for i in range(30)],
                                            'confidence_analysis': ca, 'num_scenarios': 30, 'total_requested': 30})
update_candles_session_status(child, 'finished')
update_monte_carlo_session_status(ids['monte_carlo'], 'finished')

store_significance_test_session(ids['significance'], 'running', {'form': {**form, 'n_simulations': 2000}})
update_significance_test_session_results(ids['significance'], {'observed_mean': 0.0012, 'annualized_return': 0.31,
    'p_value': 0.021, 'n_simulations': 2000, 'n_observations': 180})
update_significance_test_session_status(ids['significance'], 'finished')

ExchangeApiKeys.create(id=ids['key'], exchange_name='Bybit USDT Perpetual', name='e2e fake key', api_key=__API_KEY__,
                       api_secret=__API_SECRET__, additional_fields=json.dumps({'passphrase': __PASSPHRASE__}),
                       created_at=datetime.datetime.now())
live_session_repository.store_live_session(ids['live'], 'stopped', 'papertrade', 'Bybit USDT Perpetual',
    {'form': {**form, 'exchange': 'Bybit USDT Perpetual', 'exchange_api_key_id': ids['key'], 'notification_api_key_id': None}})
live_session_repository.store_live_session_exception(ids['live'], f'AuthenticationError: key {__API_KEY__} was rejected',
                                                     f'Traceback (most recent call last):\n  signed with {__API_SECRET__}\n')
now = jh.now_to_timestamp(True)
for i in range(25):
    trade_id = str(uuid.uuid4())
    opened = now - (30 - i) * 3600000
    ClosedTrade.insert(id=trade_id, session_id=ids['live'], strategy_name='Demo', symbol='BTC-USDT', exchange='Bybit USDT Perpetual',
                       type='long', timeframe='1h', opened_at=opened, closed_at=opened + 1800000, leverage=2, created_at=opened,
                       updated_at=opened, session_mode='papertrade').execute()
    for side, price, at in (('buy', 100.0 + i, opened), ('sell', 101.0 + i, opened + 1800000)):
        Order.insert(id=str(uuid.uuid4()), trade_id=trade_id, session_id=ids['live'], symbol='BTC-USDT', exchange='Bybit USDT Perpetual',
                     side=side, type='MARKET', reduce_only=side == 'sell', qty=0.5 if side == 'buy' else -0.5,
                     filled_qty=0.5 if side == 'buy' else -0.5, price=price, status='EXECUTED', created_at=at, updated_at=at,
                     executed_at=at, session_mode='papertrade', vars={}).execute()
LiveEquitySnapshot.insert_many([{'session_id': ids['live'], 'timestamp': now - (500 - m) * 60000, 'currency': 'USDT',
                                 'equity': 1000 + m / 10} for m in range(500)]).execute()
for i in range(50):
    store_log_into_db({'id': str(uuid.uuid4()), 'session_id': ids['live'], 'timestamp': now - (50 - i) * 1000,
                       'message': f'info message {i}'}, 'info')
store_log_into_db({'id': str(uuid.uuid4()), 'session_id': ids['live'], 'timestamp': now,
                   'message': f'order rejected, passphrase {__PASSPHRASE__} invalid'}, 'error')
print(json.dumps(ids))
'''


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _hash(password: str) -> str:
    return sha256(password.encode('utf-8')).hexdigest()


def _env_file(project: Path, password: str, ports: dict, extra: dict) -> Path:
    values = {
        'PASSWORD': password,
        'APP_HOST': '127.0.0.1',
        'APP_PORT': ports['app'],
        'POSTGRES_HOST': os.environ.get('JESSE_MCP_INTEGRATION_POSTGRES_HOST', '127.0.0.1'),
        'POSTGRES_NAME': os.environ.get('JESSE_MCP_INTEGRATION_POSTGRES_NAME', 'jesse_db'),
        'POSTGRES_PORT': os.environ.get('JESSE_MCP_INTEGRATION_POSTGRES_PORT', '5432'),
        'POSTGRES_USERNAME': os.environ.get('JESSE_MCP_INTEGRATION_POSTGRES_USERNAME', 'jesse_user'),
        'POSTGRES_PASSWORD': os.environ.get('JESSE_MCP_INTEGRATION_POSTGRES_PASSWORD', 'password'),
        'POSTGRES_SCHEMA': SCHEMA,
        'POSTGRES_SSLMODE': 'disable',
        'REDIS_HOST': '127.0.0.1',
        'REDIS_PORT': '6379',
        # A Redis DB of its own, away from the developer instance's default DB 0.
        'REDIS_DB': '7',
        'REDIS_PASSWORD': '',
        'IS_DEV_ENV': 'TRUE',
        'IS_TEST_ENV': 'TRUE',
        # A closed port: no license, catalog, or telemetry request can leave the machine.
        'JESSE_API2_URL': f'http://127.0.0.1:{ports["api2"]}',
        'LSP_PORT': ports['lsp'],
        **extra,
    }
    path = project / 'e2e.env'
    path.write_text(''.join(f'{key}={value}\n' for key, value in values.items()))
    return path


def _child_env(env_file: Path, **extra) -> dict:
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(('PYTEST', 'JESSE_DISABLE_LIVE_PLUGIN', 'JESSE_TEST_SCHEMA_READY'))}
    env.update(JESSE_ENV_FILE=str(env_file), PYTHONPATH=os.pathsep.join(filter(None, [str(JESSE_ROOT), env.get('PYTHONPATH')])))
    env.update(extra)
    return env


def _start(project: Path, env: dict, with_mcp: bool = False):
    """Start `jesse run` in its own process group; the MCP worker, if any, joins that group."""
    log = open(project / 'server.log', 'wb')
    entry = RUN_WITH_MCP if with_mcp else 'from jesse import cli; cli()'
    process = subprocess.Popen(
        [sys.executable, '-c', entry, 'run', '--skip-agent-rules'],
        cwd=project, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
    )
    return process, log


def _wait_ready(url: str, password: str, process, project: Path) -> None:
    import requests
    deadline = time.monotonic() + STARTUP_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        try:
            status = requests.get(f'{url}/testing/status', headers={'Authorization': _hash(password)}, timeout=2)
            if status.status_code == 200:
                assert status.json() == {'is_test_env': True, 'postgres_schema': SCHEMA}
                return
        except requests.RequestException:
            pass
        time.sleep(0.5)
    raise AssertionError('Disposable Jesse did not start:\n' + (project / 'server.log').read_text()[-4000:])


def _stop(process, log) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)
    log.close()


def _wait_for_mcp(url: str, token: str, process, project: Path) -> int:
    """
    Wait until the dashboard's /mcp route reaches the instance's worker; return the worker's
    internal port as the worker logged it.
    """
    import requests
    deadline = time.monotonic() + STARTUP_SECONDS
    while time.monotonic() < deadline and process.poll() is None:
        # Requests sent while the worker is still loading wait in its socket's backlog, so
        # the read timeout, not a retry, covers most of the startup.
        probe = requests.post(f'{url}/mcp', headers={'Authorization': f'Bearer {token}'}, json={}, timeout=STARTUP_SECONDS)
        match = WORKER_PORT_LOG.search((project / 'server.log').read_text(errors='replace'))
        if probe.status_code != 502 and match:
            return int(match.group(1))
        time.sleep(0.3)
    raise AssertionError('The MCP worker did not start:\n' + (project / 'server.log').read_text()[-4000:])


def _listening(port: int) -> bool:
    with socket.socket() as probe:
        return probe.connect_ex(('127.0.0.1', port)) == 0


def _occupied_port() -> socket.socket:
    """A listener on a free port, standing in for whatever holds an old MCP_PORT today."""
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen()
    return sock


@pytest.fixture(scope='module')
def instance():
    from jesse.mcp.auth import dashboard_token
    project = Path(tempfile.mkdtemp(prefix='jesse-mcp-analysis-e2e-'))
    (project / 'strategies').mkdir()
    (project / 'storage').mkdir()
    password = secrets.token_hex(16)
    ports = {name: _free_port() for name in ('app', 'lsp', 'api2')}
    # An existing project's MCP_PORT, set to a port that is already taken, must not matter.
    legacy = _occupied_port()
    env_file = _env_file(project, password, ports, {'RESET_TEST_DATABASE': 'TRUE', 'MCP_PORT': legacy.getsockname()[1]})
    process, log = _start(project, _child_env(env_file), with_mcp=True)
    try:
        url = f'http://127.0.0.1:{ports["app"]}'
        _wait_ready(url, password, process, project)
        seed = subprocess.run(
            [sys.executable, '-c', SEED_SCRIPT.replace('__API_KEY__', repr(FAKE_API_KEY))
             .replace('__API_SECRET__', repr(FAKE_API_SECRET)).replace('__PASSPHRASE__', repr(FAKE_PASSPHRASE))],
            cwd=project, env=_child_env(env_file, JESSE_TEST_SCHEMA_READY=SCHEMA), capture_output=True, text=True, timeout=120,
        )
        assert seed.returncode == 0, seed.stdout[-3000:] + seed.stderr[-3000:]
        ids = json.loads(seed.stdout.strip().splitlines()[-1])
        token = dashboard_token(password)
        worker_port = _wait_for_mcp(url, token, process, project)
        yield SimpleNamespace(url=url, password=password, token=token, ids=ids, project=project,
                              ports=ports, env_file=env_file, worker_port=worker_port,
                              legacy_port=legacy.getsockname()[1])
    finally:
        _stop(process, log)
        legacy.close()
        # Shown by pytest only when a test in this module fails.
        if (project / 'server.log').exists():
            print('--- server.log ---\n' + (project / 'server.log').read_text(errors='replace')[-6000:])
        shutil.rmtree(project, ignore_errors=True)


def _mcp(instance, scenario):
    """Run `scenario(session)` with an initialized SDK client connected through the dashboard's /mcp route."""
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async def run():
        headers = {'Authorization': f'Bearer {instance.token}'}
        async with httpx.AsyncClient(headers=headers, trust_env=False, timeout=120) as http_client:
            async with streamable_http_client(f'{instance.url}/mcp', http_client=http_client) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await scenario(session)

    return asyncio.run(run())


async def _call(session, name: str, arguments: dict) -> dict:
    result = await session.call_tool(name, arguments)
    assert result.content, name
    assert not result.isError, f'{name}: {result.content[0].text}'
    return json.loads(result.content[0].text)


def test_authentication_is_required_everywhere(instance):
    import requests
    for route in ('/session-results/get', '/session-results/live-sessions', '/session-results/live-trades',
                  '/session-results/live-orders', '/analysis/run', '/analysis/artifact'):
        assert requests.post(f'{instance.url}{route}', json={}, timeout=10).status_code == 401
        assert requests.post(f'{instance.url}{route}', json={}, headers={'Authorization': 'wrong'}, timeout=10).status_code == 401
    assert requests.post(f'{instance.url}/mcp', json={}, timeout=10).status_code == 401
    assert requests.post(f'{instance.url}/mcp', json={}, headers={'Authorization': 'Bearer wrong'}, timeout=10).status_code == 401


def test_results_of_every_session_type_through_the_mcp_client(instance):
    ids = instance.ids

    async def scenario(session):
        tools = {tool.name for tool in (await session.list_tools()).tools}
        out = {'tools': tools}
        out['summary_a'] = await _call(session, 'get_session_results', {'session_type': 'backtest', 'session_id': ids['backtest_a']})
        out['trades'] = await _call(session, 'get_session_results', {'session_type': 'backtest', 'session_id': ids['backtest_a'],
                                                                      'section': 'trades', 'offset': 30, 'limit': 15})
        out['equity'] = await _call(session, 'get_session_results', {'session_type': 'backtest', 'session_id': ids['backtest_a'],
                                                                      'section': 'equity_curve', 'offset': 0, 'limit': 50})
        out['logs'] = await _call(session, 'get_session_results', {'session_type': 'backtest', 'session_id': ids['backtest_a'],
                                                                    'section': 'logs', 'limit': 3})
        out['running'] = await _call(session, 'get_session_results', {'session_type': 'backtest', 'session_id': ids['backtest_running']})
        out['optimization'] = await _call(session, 'get_session_results', {'session_type': 'optimization', 'session_id': ids['optimization']})
        out['trials'] = await _call(session, 'get_session_results', {'session_type': 'optimization', 'session_id': ids['optimization'],
                                                                      'section': 'best_trials', 'offset': 10})
        out['mc'] = await _call(session, 'get_session_results', {'session_type': 'monte_carlo', 'session_id': ids['monte_carlo']})
        out['mc_curve_pages'] = []
        offset = 0
        while offset is not None:
            page = await _call(session, 'get_session_results', {'session_type': 'monte_carlo', 'session_id': ids['monte_carlo'],
                                                                 'section': 'equity_curves', 'offset': offset, 'limit': 500})
            out['mc_curve_pages'].append(page)
            offset = page['next_offset']
        out['mc_metrics'] = await _call(session, 'get_session_results', {'session_type': 'monte_carlo', 'session_id': ids['monte_carlo'],
                                                                          'section': 'scenario_metrics', 'limit': 500})
        out['significance'] = await _call(session, 'get_session_results', {'session_type': 'significance_test', 'session_id': ids['significance']})
        out['live'] = await _call(session, 'get_session_results', {'session_type': 'live', 'session_id': ids['live']})
        out['live_trades'] = await _call(session, 'get_session_results', {'session_type': 'live', 'session_id': ids['live'],
                                                                           'section': 'closed_trades', 'limit': 10})
        out['live_equity'] = await _call(session, 'get_session_results', {'session_type': 'live', 'session_id': ids['live'],
                                                                           'section': 'equity_curve', 'offset': 490, 'limit': 20})
        out['live_errors'] = await _call(session, 'get_session_results', {'session_type': 'live', 'session_id': ids['live'],
                                                                           'section': 'error_logs'})
        out['live_logs'] = await _call(session, 'get_session_results', {'session_type': 'live', 'session_id': ids['live'],
                                                                         'section': 'logs', 'limit': 5})
        out['live_list'] = await _call(session, 'get_live_sessions', {})
        out['missing'] = await _call(session, 'get_session_results', {'session_type': 'backtest', 'session_id': str(__import__('uuid').uuid4())})
        return out

    out = _mcp(instance, scenario)

    assert {'get_session_results', 'get_live_sessions', 'run_analysis', 'get_analysis_job', 'get_analysis_artifact',
            'cancel_analysis_job', 'delete_analysis_job'} <= out['tools']
    summary = out['summary_a']
    assert summary['status'] == 'success' and summary['session_status'] == 'finished'
    assert summary['metrics']['sharpe_ratio'] == 0.8 and summary['metrics']['serenity_index'] is None
    assert summary['sections']['trades'] == {'count': 40}
    assert summary['sections']['equity_curve']['series'] == [{'name': 'Portfolio', 'points': 181}, {'name': 'BTC-USDT', 'points': 181}]
    assert (out['trades']['returned'], out['trades']['next_offset'], out['trades']['has_more']) == (10, None, False)
    assert out['equity']['next_offset'] == 50 and len(out['equity']['items'][0]['points']) == 50
    assert out['logs']['items'] == [f'[2025-01-01] ==> log line {i}' for i in (297, 298, 299)] and out['logs']['total'] == 300
    assert 'Still running' in out['running']['status_note'] and out['running']['metrics'] is None

    assert out['optimization']['completed_trials'] == 60 and len(out['optimization']['leading_trials']) == 3
    assert [t['trial'] for t in out['trials']['items']] == ['Trial 20', 'Trial 21']

    candles = out['mc']['pipelines']['candles']
    assert (candles['status'], candles['num_scenarios']) == ('finished', 30)
    assert {m['metric'] for m in candles['summary_metrics']} >= {'sharpe_ratio', 'max_drawdown'}
    # Results stored in chunks by the real model are read back completely, page by page.
    pages = out['mc_curve_pages']
    assert len(pages) > 1 and pages[0]['truncated_by_size'] is True  # 31 curves exceed one 128 KiB page
    assert [c['scenario'] for page in pages for c in page['items']] == ['original', *range(30)]
    assert all(len(json.dumps(page['items'], separators=(',', ':'))) <= 128 * 1024 for page in pages)
    assert out['mc_metrics']['total'] == 31 and out['mc_metrics']['items'][-1]['metrics']['net_profit_percentage'] == 30

    assert out['significance']['results']['p_value'] == 0.021

    live = out['live']
    everything = json.dumps(out, default=list)
    for secret in (FAKE_API_KEY, FAKE_API_SECRET, FAKE_PASSPHRASE):
        assert secret not in everything
    assert live['session_mode'] == 'papertrade' and live['counts']['trades'] == 25 and live['counts']['equity_points'] == 500
    assert live['error']['exception'] == 'AuthenticationError: key [redacted] was rejected'
    trade = out['live_trades']['items'][0]
    assert trade['entry_price'] == 100.0 and trade['exit_price'] == 101.0 and trade['orders_count'] == 2
    assert trade['pnl'] == pytest.approx(0.5)  # computed by Jesse from the executed orders
    assert out['live_trades']['next_offset'] == 10
    assert len(out['live_equity']['items']) == 10 and out['live_equity']['has_more'] is False
    assert out['live_errors']['items'][0]['message'] == 'order rejected, passphrase [redacted] invalid'
    assert [e['message'] for e in out['live_logs']['items']] == [f'info message {i}' for i in range(45, 50)]
    assert out['live_list']['sessions'][0]['id'] == instance.ids['live']
    assert out['missing']['error_type'] == 'not_found'


CHART = '''
import json
import matplotlib.pyplot as plt
import pandas as pd

manifest = json.load(open("inputs/manifest.json"))
print("inputs", [m["name"] for m in manifest])
fig, (top, bottom) = plt.subplots(2, 1, figsize=(10, 7))
for name in ("base", "tuned"):
    data = json.load(open(f"inputs/{name}.json"))
    portfolio = next(s for s in data["equity_curve"] if s["name"] == "Portfolio")
    frame = pd.DataFrame(portfolio["data"])
    frame["time"] = pd.to_datetime(frame["time"], unit="s")
    top.plot(frame["time"], frame["value"], label=f"{name} sharpe={data['metrics']['sharpe_ratio']}")
    print(name, "trades", len(data["trades"]))
top.legend()
mc = json.load(open("inputs/mc.json"))["pipelines"]["candles"]
finals = [s["equity_curve"][0]["data"][-1]["value"] for s in mc["scenarios"]]
bottom.hist(finals, bins=10)
print("mc scenarios", len(mc["scenarios"]))
live = json.load(open("inputs/live.json"))
print("live trades", len(live["closed_trades"]), "equity points", len(live["equity_curve"]))
fig.savefig("output/comparison.png", dpi=100, bbox_inches="tight")
plt.close(fig)
pd.DataFrame({"final": finals}).describe().to_csv("output/mc_finals.csv")
'''


def test_analysis_snapshot_chart_and_image_content_through_the_mcp_client(instance):
    from PIL import Image
    ids = instance.ids
    inputs = [
        {'session_type': 'backtest', 'session_id': ids['backtest_a'], 'name': 'base'},
        {'session_type': 'backtest', 'session_id': ids['backtest_b'], 'name': 'tuned'},
        {'session_type': 'monte_carlo', 'session_id': ids['monte_carlo'], 'name': 'mc'},
        {'session_type': 'live', 'session_id': ids['live'], 'name': 'live'},
    ]

    async def scenario(session):
        started = await _call(session, 'run_analysis', {'code': CHART, 'inputs': inputs})
        job_id = started['job']['id']
        deadline = time.monotonic() + 120
        while True:
            status = await _call(session, 'get_analysis_job', {'job_id': job_id, 'tail_lines': 50})
            if status['job']['status'] != 'running' or time.monotonic() > deadline:
                break
            await asyncio.sleep(0.5)
        image = await session.call_tool('get_analysis_artifact', {'job_id': job_id, 'path': 'comparison.png'})
        table = await session.call_tool('get_analysis_artifact', {'job_id': job_id, 'path': 'mc_finals.csv'})
        escape = await session.call_tool('get_analysis_artifact', {'job_id': job_id, 'path': '../inputs/live.json'})
        snapshot = await session.call_tool('get_analysis_artifact', {'job_id': job_id, 'path': 'inputs/live.json'})
        failing = await _call(session, 'run_analysis', {'code': 'raise RuntimeError("broken analysis")'})
        while (await _call(session, 'get_analysis_job', {'job_id': failing['job']['id']}))['job']['status'] == 'running':
            await asyncio.sleep(0.2)
        failed = await _call(session, 'get_analysis_job', {'job_id': failing['job']['id']})
        sleeper = await _call(session, 'run_analysis', {'code': 'import subprocess, sys, time\n'
                                                                 'subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])\n'
                                                                 'time.sleep(300)\n'})
        await asyncio.sleep(1)
        cancelled = await _call(session, 'cancel_analysis_job', {'job_id': sleeper['job']['id']})
        deleted = await _call(session, 'delete_analysis_job', {'job_id': failing['job']['id']})
        gone = await _call(session, 'get_analysis_job', {'job_id': failing['job']['id']})
        return started, status, image, table, escape, snapshot, failed, cancelled, deleted, gone

    started, status, image, table, escape, snapshot, failed, cancelled, deleted, gone = _mcp(instance, scenario)

    job = status['job']
    assert started['job']['status'] == 'running' and [i['name'] for i in started['job']['inputs']] == ['base', 'tuned', 'mc', 'live']
    assert job['status'] == 'succeeded', status['output']
    assert "inputs ['base', 'tuned', 'mc', 'live']" in status['output']
    assert 'base trades 40' in status['output'] and 'tuned trades 25' in status['output']
    assert 'mc scenarios 30' in status['output'] and 'live trades 25 equity points 500' in status['output']
    assert {a['path'] for a in status['artifacts']} == {'comparison.png', 'mc_finals.csv'}

    assert not image.isError and [c.type for c in image.content] == ['text', 'image']
    png = base64.b64decode(image.content[1].data)
    assert image.content[1].mimeType == 'image/png'
    with Image.open(io.BytesIO(png)) as decoded:
        assert decoded.format == 'PNG' and decoded.size == (json.loads(image.content[0].text)['width'],
                                                             json.loads(image.content[0].text)['height'])
    assert 'count' in json.loads(table.content[0].text)['content']
    assert escape.isError and json.loads(escape.content[0].text)['error_type'] == 'invalid_path'
    assert snapshot.isError and json.loads(snapshot.content[0].text)['error_type'] == 'not_found'

    workspace = instance.project / 'storage' / 'mcp' / 'analysis' / job['id']
    live_snapshot = (workspace / 'inputs' / 'live.json').read_text()
    for secret in (FAKE_API_KEY, FAKE_API_SECRET, FAKE_PASSPHRASE):
        assert secret not in live_snapshot
    assert not (instance.project / 'research_scripts').exists()

    assert failed['job']['status'] == 'failed' and 'RuntimeError: broken analysis' in failed['output']
    assert cancelled['job']['status'] == 'cancelled'
    assert deleted['deleted'] is True and gone['error_type'] == 'not_found'


def test_earlier_tools_still_work_through_the_same_client(instance):
    ids = instance.ids

    async def scenario(session):
        out = {}
        out['backtest'] = await _call(session, 'get_backtest_session', {'session_id': ids['backtest_a']})
        out['backtests'] = await _call(session, 'get_backtest_sessions', {'limit': 10})
        out['optimization'] = await _call(session, 'get_optimization_session', {'session_id': ids['optimization']})
        out['monte_carlo'] = await _call(session, 'get_monte_carlo_session', {'session_id': ids['monte_carlo']})
        out['significance'] = await _call(session, 'get_significance_test_session', {'session_id': ids['significance']})
        out['write'] = await _call(session, 'write_project_file', {'path': 'research_scripts/e2e.py', 'content': 'print("e2e ok")\n'})
        out['read'] = await _call(session, 'read_project_file', {'path': 'research_scripts/e2e.py'})
        out['run'] = await _call(session, 'run_research_script', {'path': 'research_scripts/e2e.py'})
        while (await _call(session, 'get_research_job_status', {'job_id': out['run']['job']['id']}))['job']['status'] == 'running':
            await asyncio.sleep(0.2)
        out['output'] = await _call(session, 'get_research_job_output', {'job_id': out['run']['job']['id']})
        out['keys'] = await session.call_tool('get_exchange_api_keys', {})
        out['resource'] = await session.read_resource('jesse://session_analysis')
        return out

    out = _mcp(instance, scenario)
    assert out['backtest']['data']['session']['metrics']['total'] == 40
    assert ids['backtest_a'] in [s['id'] for s in out['backtests']['sessions']]
    assert out['optimization']['data']['session']['completed_trials'] == 60
    assert out['monte_carlo']['data']['session']['candles_session']['status'] == 'finished'
    assert out['significance']['data']['session']['results']['p_value'] == 0.021
    assert out['write']['status'] == 'success' and out['read']['content'] == 'print("e2e ok")\n'
    assert out['output']['output'] == 'e2e ok\n'
    keys_text = out['keys'].content[0].text
    assert 'e2e fake key' in keys_text and FAKE_API_KEY not in keys_text and FAKE_API_SECRET not in keys_text
    assert 'run_analysis' in out['resource'].contents[0].text


# Ignores SIGTERM, so cancelling it waits out Jesse's full 5-second grace period before SIGKILL.
STUBBORN_SCRIPT = '''
import signal, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
print("ready", flush=True)
time.sleep(120)
'''
STRATEGY_SOURCE = '''from jesse.strategies import Strategy


class E2EStrategy(Strategy):
    def should_long(self) -> bool:
        return False

    def go_long(self):
        pass
'''


def test_a_slow_call_does_not_stall_others_and_strategy_folders_are_managed(instance):
    """Through the real /mcp route: offloaded tools answer concurrently; whole strategy folders move and delete."""
    import anyio

    async def scenario(session):
        out = {}
        await _call(session, 'write_project_file', {'path': 'research_scripts/stubborn.py', 'content': STUBBORN_SCRIPT})
        job_id = (await _call(session, 'run_research_script', {'path': 'research_scripts/stubborn.py'}))['job']['id']
        while 'ready' not in (await _call(session, 'get_research_job_output', {'job_id': job_id}))['output']:
            await asyncio.sleep(0.1)

        async def cancel():
            out['cancelled'] = await _call(session, 'cancel_research_job', {'job_id': job_id})
            out['cancel_seconds'] = time.monotonic() - started

        started = time.monotonic()
        async with anyio.create_task_group() as tg:
            tg.start_soon(cancel)
            await asyncio.sleep(0.5)
            out['listed'] = await _call(session, 'list_project_files', {'path': 'research_scripts'})
            out['list_seconds'] = time.monotonic() - started
            out['cancel_pending_while_listed'] = 'cancelled' not in out

        out['created'] = await _call(session, 'create_strategy', {'name': 'E2EStrategy', 'content': STRATEGY_SOURCE})
        out['renamed'] = await _call(session, 'move_project_path',
                                     {'source': 'strategies/E2EStrategy', 'destination': 'strategies/E2ERenamed'})
        out['read_renamed'] = await _call(session, 'read_strategy', {'name': 'E2ERenamed'})
        out['copied'] = await _call(session, 'copy_project_path',
                                    {'source': 'strategies/E2ERenamed', 'destination': 'strategies/E2ECopy'})
        out['not_empty'] = await _call(session, 'delete_project_path', {'path': 'strategies/E2ECopy'})
        out['deleted_copy'] = await _call(session, 'delete_project_path', {'path': 'strategies/E2ECopy', 'recursive': True})
        out['deleted_renamed'] = await _call(session, 'delete_project_path',
                                             {'path': 'strategies/E2ERenamed', 'recursive': True})
        out['root'] = await _call(session, 'delete_project_path', {'path': 'strategies', 'recursive': True})
        out['listing'] = await _call(session, 'list_project_files', {'path': 'strategies'})
        return out

    out = _mcp(instance, scenario)

    assert out['cancelled']['job']['status'] == 'cancelled' and out['cancel_seconds'] >= 4
    assert out['cancel_pending_while_listed'] is True and out['list_seconds'] < 3
    assert out['listed']['status'] == 'success'

    assert out['created']['status'] == 'success'
    assert out['renamed']['type'] == 'directory'
    # The generic move leaves the code alone; the class keeps its old name until it is edited.
    assert out['read_renamed']['content'] == STRATEGY_SOURCE
    assert out['copied']['status'] == 'success' and out['not_empty']['error_type'] == 'directory_not_empty'
    assert out['deleted_copy']['status'] == out['deleted_renamed']['status'] == 'success'
    assert out['root']['error_type'] == 'protected_path'
    assert out['listing']['entries'] == []
    assert (instance.project / 'strategies').is_dir()


class _UsageBackend:
    """
    Stands in for the licensing backend on the instance's api2 port (otherwise closed): holds
    each POST /usage, the metered run tools' usage check, until `release` is set, then allows
    it. Everything else gets a 404 at once.
    """

    def __init__(self, port: int) -> None:
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        self.release = threading.Event()
        self.lock = threading.Lock()
        self.checks = 0
        backend = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length') or 0))
                if self.path != '/usage':
                    self.send_error(404)
                    return
                with backend.lock:
                    backend.checks += 1
                # Well under the worker's 10-second timeout for this request.
                backend.release.wait(8)
                body = json.dumps({'allowed': True, 'remaining': 99, 'limit': 100, 'tier': 'free'}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        ThreadingHTTPServer.allow_reuse_address = True
        self.server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> '_UsageBackend':
        self.thread.start()
        return self

    def __exit__(self, *_exc) -> None:
        self.release.set()
        self.server.shutdown()
        self.server.server_close()


def test_older_tools_answer_while_a_metered_run_waits_for_its_usage_check(instance):
    """
    Through the real /mcp route: while run_significance_test waits for its usage check, other
    older tools still answer; a cancelled run is still checked and attempted exactly once
    (it names a session that does not exist, so nothing starts) and the session survives.
    """
    import anyio
    import httpx
    import uuid
    from mcp.types import LATEST_PROTOCOL_VERSION

    ids = instance.ids
    missing = str(uuid.uuid4())

    async def concurrent(session):
        out = {}

        async def run():
            out['run'] = await _call(session, 'run_significance_test', {'session_id': missing})

        async with anyio.create_task_group() as tg:
            tg.start_soon(run)
            while usage.checks < 1:
                await asyncio.sleep(0.05)
            started = time.monotonic()
            await session.send_ping()
            out['backtest'] = await _call(session, 'get_backtest_session', {'session_id': ids['backtest_a']})
            out['candles'] = await _call(session, 'get_existing_candles', {})
            out['indicators'] = await _call(session, 'list_indicators', {})
            out['tools'] = await session.list_tools()
            out['others_seconds'] = time.monotonic() - started
            out['run_pending'] = 'run' not in out
            usage.release.set()
        return out

    async def cancelled():
        headers = {'Authorization': f'Bearer {instance.token}', 'Accept': 'application/json, text/event-stream'}
        async with httpx.AsyncClient(timeout=30, trust_env=False) as http:
            init = await http.post(f'{instance.url}/mcp', headers=headers, json={
                'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                'params': {'protocolVersion': LATEST_PROTOCOL_VERSION, 'capabilities': {}, 'clientInfo': {'name': 'e2e', 'version': '1'}},
            })
            session_headers = {**headers, 'mcp-session-id': init.headers['mcp-session-id'],
                               'mcp-protocol-version': init.json()['result']['protocolVersion']}
            await http.post(f'{instance.url}/mcp', headers=session_headers, json={'jsonrpc': '2.0', 'method': 'notifications/initialized'})
            out = {}

            async def call():
                reply = await http.post(f'{instance.url}/mcp', headers=session_headers, json={
                    'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call',
                    'params': {'name': 'run_significance_test', 'arguments': {'session_id': missing}}})
                out['reply'] = reply.json()

            async with anyio.create_task_group() as tg:
                tg.start_soon(call)
                while usage.checks < 2:
                    await asyncio.sleep(0.05)
                await http.post(f'{instance.url}/mcp', headers=session_headers, json={
                    'jsonrpc': '2.0', 'method': 'notifications/cancelled', 'params': {'requestId': 7, 'reason': 'e2e'}})
                cancel_sent = time.monotonic()
                while 'reply' not in out:
                    await asyncio.sleep(0.05)
                out['reply_seconds'] = time.monotonic() - cancel_sent
                usage.release.set()
            log = instance.project / 'server.log'
            deadline = time.monotonic() + 15
            while 'finished after its MCP request was cancelled' not in log.read_text(errors='replace') and time.monotonic() < deadline:
                await asyncio.sleep(0.1)
            await asyncio.sleep(0.5)
            listed = await http.post(f'{instance.url}/mcp', headers=session_headers, json={'jsonrpc': '2.0', 'id': 8, 'method': 'tools/list'})
            out['listed'] = listed.json()
            return out

    with _UsageBackend(instance.ports['api2']) as usage:
        first = _mcp(instance, concurrent)
        usage.release.clear()
        second = asyncio.run(cancelled())
        checks = usage.checks

    assert first['run_pending'] is True and first['others_seconds'] < 3
    assert first['backtest']['data']['session']['metrics']['total'] == 40
    assert first['candles']['status'] == 'success' and first['indicators']['count'] > 100
    assert len(first['tools'].tools) == REGISTERED_TOOL_COUNT
    assert first['run'] == {'status': 'error', 'message': f'Session {missing} not found'}

    assert second['reply']['error']['message'] == 'Request cancelled' and second['reply_seconds'] < 3
    assert len(second['listed']['result']['tools']) == REGISTERED_TOOL_COUNT
    # One usage check per call: nothing was retried after the cancellation.
    assert checks == 2
    assert ('run_significance_test_service finished after its MCP request was cancelled or its session closed '
            '(status: error).') in (instance.project / 'server.log').read_text(errors='replace')


def test_live_results_are_refused_without_the_live_plugin(instance):
    """A second instance on the same (already seeded) schema with the live plugin disabled."""
    import requests
    project = Path(tempfile.mkdtemp(prefix='jesse-mcp-analysis-e2e-noplugin-'))
    (project / 'strategies').mkdir()
    (project / 'storage').mkdir()
    ports = {name: _free_port() for name in ('app', 'lsp', 'api2')}
    env_file = _env_file(project, instance.password, ports, {'RESET_TEST_DATABASE': 'FALSE', 'JESSE_DISABLE_LIVE_PLUGIN': 'TRUE'})
    process, log = _start(project, _child_env(env_file, JESSE_DISABLE_LIVE_PLUGIN='TRUE'))
    try:
        url = f'http://127.0.0.1:{ports["app"]}'
        _wait_ready(url, instance.password, process, project)
        headers = {'Authorization': _hash(instance.password)}
        live = requests.post(f'{url}/session-results/get', headers=headers, timeout=30,
                             json={'session_type': 'live', 'session_id': instance.ids['live']})
        assert live.status_code == 403 and live.json()['error_type'] == 'live_plugin_unavailable'
        listing = requests.post(f'{url}/session-results/live-sessions', headers=headers, json={}, timeout=30)
        assert listing.status_code == 403
        backtest = requests.post(f'{url}/session-results/get', headers=headers, timeout=30,
                                 json={'session_type': 'backtest', 'session_id': instance.ids['backtest_a']})
        assert backtest.status_code == 200 and backtest.json()['metrics']['total'] == 40
        refused = requests.post(f'{url}/analysis/run', headers=headers, timeout=30, json={
            'code': 'print(1)', 'inputs': [{'session_type': 'live', 'session_id': instance.ids['live']}]})
        assert refused.status_code == 403
        for route in ('live-trades', 'live-orders'):
            history = requests.post(f'{url}/session-results/{route}', headers=headers, json={'recent_days': 3}, timeout=30)
            assert history.status_code == 403 and history.json()['error_type'] == 'live_plugin_unavailable'
        refused = requests.post(f'{url}/analysis/run', headers=headers, timeout=30, json={
            'code': 'print(1)', 'inputs': [{'dataset': 'live_trades', 'recent_days': 3}]})
        assert refused.status_code == 403
        root = project / 'storage' / 'mcp' / 'analysis'
        # No workspace is created for a refused dataset input (the folder itself may exist).
        assert not root.exists() or not [p for p in root.iterdir() if not p.name.startswith('.trash-')]
    finally:
        _stop(process, log)
        shutil.rmtree(project, ignore_errors=True)


def test_the_worker_port_is_internal_and_the_legacy_setting_is_ignored(instance):
    import requests
    log = (instance.project / 'server.log').read_text(errors='replace')

    assert 'MCP_PORT in your .env file is no longer used and can be removed' in log
    assert instance.worker_port != instance.legacy_port
    assert 'MCP Server is running at' in log and f'{instance.url}/mcp' in log
    # The worker's address is never printed as an endpoint; only its own log line names the port.
    assert f'127.0.0.1:{instance.worker_port}' not in log
    assert f'internal loopback port {instance.worker_port}; clients connect to {instance.url}/mcp' in log
    # The worker enforces the token on its own port too.
    assert requests.post(f'http://127.0.0.1:{instance.worker_port}/mcp', json={}, timeout=30).status_code == 401


async def _tools_and_indicators(url: str, token: str):
    """Initialize an SDK session through `url`/mcp; return its tool count and indicator count."""
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with httpx.AsyncClient(headers={'Authorization': f'Bearer {token}'}, trust_env=False, timeout=120) as http_client:
        async with streamable_http_client(f'{url}/mcp', http_client=http_client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                indicators = await _call(session, 'list_indicators', {})
                return len(tools.tools), indicators['count']


def test_two_instances_run_their_own_workers_side_by_side(instance):
    """A second instance on the same machine and schema, with its own password and worker."""
    import requests
    from jesse.mcp.auth import dashboard_token
    project = Path(tempfile.mkdtemp(prefix='jesse-mcp-analysis-e2e-second-'))
    (project / 'strategies').mkdir()
    (project / 'storage').mkdir()
    password = secrets.token_hex(16)
    token = dashboard_token(password)
    ports = {name: _free_port() for name in ('app', 'lsp', 'api2')}
    # Both instances carry the same stale MCP_PORT, which used to make the second one fail.
    env_file = _env_file(project, password, ports, {'RESET_TEST_DATABASE': 'FALSE', 'MCP_PORT': instance.legacy_port})
    process, log = _start(project, _child_env(env_file), with_mcp=True)
    try:
        url = f'http://127.0.0.1:{ports["app"]}'
        _wait_ready(url, password, process, project)
        worker_port = _wait_for_mcp(url, token, process, project)
        assert worker_port not in (instance.worker_port, instance.legacy_port)

        async def both():
            return await asyncio.gather(
                _tools_and_indicators(instance.url, instance.token), _tools_and_indicators(url, token),
            )

        first, second = asyncio.run(both())
        assert first == second and first[0] == REGISTERED_TOOL_COUNT and first[1] > 100

        # Neither instance's route nor its worker accepts the other instance's token.
        for route, foreign_token in ((instance.url, token), (url, instance.token)):
            assert requests.post(f'{route}/mcp', headers={'Authorization': f'Bearer {foreign_token}'},
                                 json={}, timeout=30).status_code == 401
        for port, foreign_token in ((instance.worker_port, token), (worker_port, instance.token)):
            assert requests.post(f'http://127.0.0.1:{port}/mcp', headers={'Authorization': f'Bearer {foreign_token}'},
                                 json={}, timeout=30).status_code == 401
    finally:
        _stop(process, log)
        shutil.rmtree(project, ignore_errors=True)

    # Stopping the second instance released its worker's port and left the first one serving.
    deadline = time.monotonic() + 15
    while _listening(worker_port) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not _listening(worker_port)
    assert asyncio.run(_tools_and_indicators(instance.url, instance.token)) == first


FAKE_LICENSE = 'E2E-FAKE-LICENSE-TOKEN-4242'
CATALOG_SESSION_TOKEN = 'e2e-fake-jesse-trade-session'
CATALOG_CODE = STRATEGY_SOURCE.replace('E2EStrategy', 'E2ECatalogImport')


class _CatalogBackend:
    """
    Stands in for jesse.trade's catalog and licensing API on an instance's api2 port. Like the
    real service, it exchanges only FAKE_LICENSE (while `accept_license` is set) for a session
    token and includes a strategy's code only for that token. Requests to a path in `hold`
    wait for `release` (at most 8 s, under Jesse's 10-second timeout for these requests).
    Every request is recorded as (method, path, Authorization header, JSON body).
    """

    def __init__(self, port: int) -> None:
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from urllib.parse import urlsplit

        self.accept_license = True
        self.hold: set = set()
        self.release = threading.Event()
        self.lock = threading.Lock()
        self.requests: list = []
        backend = self

        class Handler(BaseHTTPRequestHandler):
            def _handle(self, method: str) -> None:
                path = urlsplit(self.path).path
                length = int(self.headers.get('Content-Length') or 0)
                body = json.loads(self.rfile.read(length)) if length else None
                authorization = self.headers.get('Authorization')
                with backend.lock:
                    backend.requests.append((method, path, authorization, body))
                if path in backend.hold:
                    backend.release.wait(8)
                status, payload = backend.reply(method, path, authorization, body)
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                self._handle('GET')

            def do_POST(self):
                self._handle('POST')

            def log_message(self, *_args):
                pass

        ThreadingHTTPServer.allow_reuse_address = True
        self.server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def reply(self, method: str, path: str, authorization, body) -> tuple:
        unlocked = authorization == f'Bearer {CATALOG_SESSION_TOKEN}'
        entry = {'slug': 'e2e-catalog', 'name': 'E2E Catalog', 'type': 'free', 'user': {'username': 'e2e'},
                 'description': 'seeded catalog entry', 'code': CATALOG_CODE if unlocked else None,
                 'strategy_metrics': {'sharpe_ratio': 1.4, 'net_profit_percentage': 22.0}}
        if (method, path) == ('POST', '/auth/exchange-token'):
            if self.accept_license and (body or {}).get('license_api_token') == FAKE_LICENSE:
                return 200, {'access_token': CATALOG_SESSION_TOKEN, 'user': {'username': 'e2e'}}
            return 401, {'message': 'Invalid license API token'}
        if (method, path) == ('GET', '/strategies/periods'):
            return 200, {'periods': ['Q4 of 2025', 'Q1 of 2026']}
        if (method, path) == ('GET', '/strategies'):
            return 200, {'strategies': [entry]}
        if (method, path) == ('GET', '/strategies/e2e-catalog'):
            return 200, entry
        return 404, {'message': 'Not found'}

    def paths(self) -> list:
        with self.lock:
            return [(method, path) for method, path, _, _ in self.requests]

    def __enter__(self) -> '_CatalogBackend':
        self.thread.start()
        return self

    def __exit__(self, *_exc) -> None:
        self.release.set()
        self.server.shutdown()
        self.server.server_close()


def test_catalog_and_license_routes_keep_their_checks_and_do_not_stall_the_api_or_mcp(instance):
    """
    A third instance with a fake LICENSE_API_TOKEN, whose api2 port is served by a local
    stand-in for jesse.trade (JESSE_API_URL points at a closed port, so nothing leaves the
    machine). Dashboard authentication and the license checks answer as before, and while
    jesse.trade is slow to answer, the dashboard API and the MCP tools, including results of
    the seeded sessions, still answer at once.
    """
    import anyio
    import requests
    import threading
    from jesse.mcp.auth import dashboard_token

    project = Path(tempfile.mkdtemp(prefix='jesse-mcp-analysis-e2e-catalog-'))
    (project / 'strategies').mkdir()
    (project / 'storage').mkdir()
    password = secrets.token_hex(16)
    token = dashboard_token(password)
    ports = {name: _free_port() for name in ('app', 'lsp', 'api2', 'api1')}
    env_file = _env_file(project, password, ports, {
        'RESET_TEST_DATABASE': 'FALSE', 'LICENSE_API_TOKEN': FAKE_LICENSE,
        'JESSE_API_URL': f'http://127.0.0.1:{ports["api1"]}/api',
    })
    dashboard = {'Authorization': _hash(password)}
    routes = [('GET', '/strategy/index', {'params': {'period': 'Q1 of 2026'}}), ('GET', '/strategy/periods', {}),
              ('GET', '/strategy/jesse-trade/e2e-catalog', {}),
              ('GET', '/strategy/jesse-trade/e2e-catalog/metrics', {'params': {'period': 'Q1 of 2026', 'symbol': 'BTC-USDT', 'timeframe': '4h'}}),
              ('POST', '/strategy/import', {'json': {'slug': 'e2e-catalog'}}), ('POST', '/auth/jesse-trade-token', {})]

    with _CatalogBackend(ports['api2']) as backend:
        process, log = _start(project, _child_env(env_file), with_mcp=True)
        try:
            url = f'http://127.0.0.1:{ports["app"]}'
            _wait_ready(url, password, process, project)
            _wait_for_mcp(url, token, process, project)

            # Dashboard authentication comes first: nothing reaches jesse.trade without it.
            for method, path, kwargs in routes:
                for headers in ({}, {'Authorization': 'wrong'}, {'Authorization': password}):
                    denied = requests.request(method, url + path, headers=headers, timeout=30, **kwargs)
                    assert (denied.status_code, denied.json()) == (401, {'message': 'Invalid password'}), path
            assert backend.paths() == []

            exchanged = requests.post(f'{url}/auth/jesse-trade-token', headers=dashboard, timeout=30)
            assert exchanged.status_code == 200 and exchanged.json() == {
                'status': 'success', 'access_token': CATALOG_SESSION_TOKEN, 'user': {'username': 'e2e'}}
            assert backend.requests[-1] == ('POST', '/auth/exchange-token', None, {'license_api_token': FAKE_LICENSE})

            # Without a session token the import is refused and nothing is written.
            refused = requests.post(f'{url}/strategy/import', headers=dashboard, json={'slug': 'e2e-catalog'}, timeout=30)
            assert refused.status_code == 403 and 'Strategy code not available' in refused.json()['message']
            assert os.listdir(project / 'strategies') == []

            # A rejected license: the exchange fails, and the MCP import stops before downloading.
            backend.accept_license = False
            rejected = requests.post(f'{url}/auth/jesse-trade-token', headers=dashboard, timeout=30)
            assert rejected.status_code == 401
            assert rejected.json() == {'status': 'error', 'message': 'Failed to exchange token: {"message": "Invalid license API token"}'}

            ids = instance.ids

            async def unlicensed(session):
                return await _call(session, 'import_catalog_strategy', {'slug': 'e2e-catalog'})

            catalog_instance = SimpleNamespace(url=url, token=token)
            before = len(backend.requests)
            denied_import = _mcp(catalog_instance, unlicensed)
            assert denied_import['error_type'] == 'license_token_rejected'
            assert backend.paths()[before:] == [('POST', '/auth/exchange-token')]
            assert os.listdir(project / 'strategies') == []
            backend.accept_license = True

            # jesse.trade now holds its answers: the dashboard's periods request and the MCP
            # browse (whose first request is the same route) both wait on it.
            backend.hold.add('/strategies/periods')
            held = {}
            direct = threading.Thread(target=lambda: held.setdefault(
                'periods', requests.get(f'{url}/strategy/periods', headers=dashboard, timeout=30)))

            async def concurrent(session):
                out = {}

                async def browse():
                    out['browse'] = await _call(session, 'browse_strategy_catalog', {})

                async with anyio.create_task_group() as tg:
                    direct.start()
                    tg.start_soon(browse)
                    while backend.paths().count(('GET', '/strategies/periods')) < 2:
                        await asyncio.sleep(0.05)
                    started = time.monotonic()
                    status = await anyio.to_thread.run_sync(
                        lambda: requests.get(f'{url}/testing/status', headers=dashboard, timeout=30))
                    out['api_seconds'] = time.monotonic() - started
                    out['api_status'] = status.json()
                    await session.send_ping()
                    out['indicators'] = await _call(session, 'list_indicators', {})
                    out['backtest'] = await _call(session, 'get_session_results',
                                                  {'session_type': 'backtest', 'session_id': ids['backtest_a']})
                    out['mcp_seconds'] = time.monotonic() - started
                    out['still_held'] = 'browse' not in out and direct.is_alive()
                    backend.release.set()
                out['imported'] = await _call(session, 'import_catalog_strategy', {'slug': 'e2e-catalog'})
                out['again'] = await _call(session, 'import_catalog_strategy', {'slug': 'e2e-catalog'})
                return out

            out = _mcp(catalog_instance, concurrent)
            direct.join(30)
            imported_code = (project / 'strategies' / 'E2ECatalogImport' / '__init__.py').read_text()
            downloads = [request for request in backend.requests if request[1] == '/strategies/e2e-catalog']
        finally:
            _stop(process, log)
            shutil.rmtree(project, ignore_errors=True)

    # Both probes run while jesse.trade holds its answers for up to 8 s; the bounds leave room
    # for a loaded machine, and a blocked event loop would push them to the full hold.
    assert out['still_held'] is True
    assert out['api_status'] == {'is_test_env': True, 'postgres_schema': SCHEMA} and out['api_seconds'] < 1.5
    assert out['indicators']['count'] > 100 and out['mcp_seconds'] < 3
    assert out['backtest']['session_status'] == 'finished' and out['backtest']['metrics']['sharpe_ratio'] == 0.8
    assert held['periods'].status_code == 200 and held['periods'].json() == {'periods': ['Q4 of 2025', 'Q1 of 2026']}
    browse = out['browse']
    assert browse['status'] == 'success' and browse['jesse_trade_signed_in'] is True
    assert [(s['slug'], s['code_available']) for s in browse['strategies']] == [('e2e-catalog', True)]
    assert out['imported']['status'] == 'success' and out['imported']['local_name'] == 'E2ECatalogImport'
    assert out['again']['error_type'] == 'strategy_exists'
    assert imported_code == CATALOG_CODE
    # The dashboard's refused import sent no token; both MCP imports sent the exchanged session token.
    assert [request[2] for request in downloads] == [None, f'Bearer {CATALOG_SESSION_TOKEN}', f'Bearer {CATALOG_SESSION_TOKEN}']


# ---------------------------------------------------------------------------
# Candle management and live/paper session management
# ---------------------------------------------------------------------------

# Seeds candle rows through Jesse's Candle model in the instance's guarded schema. Every symbol
# carries an E2E prefix; the 1m series spans three of the export's 5,000-row cursor batches.
CANDLE_SEED_SCRIPT = r'''
import jesse.helpers as jh
from jesse.models.Candle import Candle
from jesse.services.db import database
database.open_connection()
T0 = 1704067200000

def rows(exchange, symbol, count, timeframe='1m', step=60000, price=100.0):
    return [{'id': jh.generate_unique_id(), 'exchange': exchange, 'symbol': symbol, 'timeframe': timeframe,
             'timestamp': T0 + i * step, 'open': price + i / 8, 'close': price + i / 8 + 0.125,
             'high': price + i / 8 + 0.5, 'low': price + i / 8 - 0.25, 'volume': 1.5 + i % 11} for i in range(count)]

for batch in (rows('Binance Perpetual Futures', 'E2EBTC-USDT', 12345),
              rows('Binance Perpetual Futures', 'E2EBTC-USDT', 100, '5m', 300000),
              rows('Binance Perpetual Futures', 'E2EETH-USDT', 50),
              rows('Bybit Spot', 'E2EBTC-USDT', 30),
              rows('Hyperliquid Perpetual', 'E2EX-USDC', 10)):
    for start in range(0, len(batch), 5000):
        Candle.insert_many(batch[start:start + 5000]).execute()

# /candles/get reads the live settings the dashboard saves on first load; store them the same way.
import json
from jesse.models.Option import Option
option = Option.get_or_none(Option.type == 'config')
settings = json.loads(option.json) if option else {}
settings['live'] = {**settings.get('live', {}), 'warm_up_candles': 20, 'generate_candles_from_1m': True}
if option:
    Option.update(json=json.dumps(settings)).where(Option.id == option.id).execute()
else:
    Option.create(id=jh.generate_unique_id(), updated_at=jh.now(True), type='config', json=json.dumps(settings))
print('seeded')
'''

# A live session record in status "running", as the live plugin leaves it; the test marks it
# active in the instance's Redis worker set instead of starting any process.
RUNNING_SESSION_SCRIPT = r'''
import json, sys
from jesse.repositories import live_session_repository
from jesse.services.db import database
database.open_connection()
live_session_repository.store_live_session(sys.argv[1], 'running', 'papertrade', 'Bybit USDT Perpetual', {'form': {
    'debug_mode': True, 'paper_mode': True, 'exchange': 'Bybit USDT Perpetual', 'exchange_api_key_id': '',
    'notification_api_key_id': '', 'routes': [{'strategy': 'E2ELive', 'symbol': 'BTC-USDT', 'timeframe': '1h'}],
    'data_routes': []}})
print('stored')
'''

E2E_LIVE_STRATEGY = 'from jesse.strategies import Strategy\n\n\nclass E2ELive(Strategy):\n    def should_long(self):\n        return False\n\n    def go_long(self):\n        pass\n'
LIVE_ROUTES = json.dumps([{'strategy': 'E2ELive', 'symbol': 'BTC-USDT', 'timeframe': '1h'}])


def _run_in_instance(instance, script: str, *args: str) -> str:
    result = subprocess.run([sys.executable, '-c', script, *args], cwd=instance.project,
                            env=_child_env(instance.env_file, JESSE_TEST_SCHEMA_READY=SCHEMA),
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    return result.stdout


def _redis():
    import redis
    return redis.Redis(host='127.0.0.1', port=6379, db=7)


def _dashboard_export(instance, exchange: str, symbol: str) -> bytes:
    """The dashboard's Export download: a native form POST carrying the auth token."""
    import requests
    response = requests.post(f'{instance.url}/candles/export', data={
        'exchange': exchange, 'symbol': symbol, 'token': _hash(instance.password)}, timeout=120)
    assert response.status_code == 200
    return response.content


def test_candle_management_round_trip_through_the_mcp_client(instance):
    """
    Inventory, PostgreSQL-streamed export, project-path Custom Data import, duplicate
    handling, copy, delete, and purge through the SDK client and the /mcp proxy. Only invalid
    imports are requested, so no exchange or provider is contacted.
    """
    import anyio

    _run_in_instance(instance, CANDLE_SEED_SCRIPT)

    async def scenario(session):
        out = {'tools': {tool.name for tool in (await session.list_tools()).tools}}
        out['inventory'] = await _call(session, 'get_existing_candles', {'symbol': 'e2e'})
        out['live_only'] = await _call(session, 'get_existing_candles', {'symbol': 'e2e', 'availability': 'live'})
        out['page'] = await _call(session, 'get_existing_candles', {'symbol': 'e2e', 'limit': 2, 'offset': 2})
        out['export'] = await _call(session, 'export_candles', {'exchange': 'Binance Perpetual Futures', 'symbol': 'E2EBTC-USDT'})
        # The dashboard's own download of the same pair, fetched before the series is deleted below.
        out['dashboard_download'] = await anyio.to_thread.run_sync(
            lambda: _dashboard_export(instance, 'Binance Perpetual Futures', 'E2EBTC-USDT'))
        out['export_again'] = await _call(session, 'export_candles', {'exchange': 'Binance Perpetual Futures', 'symbol': 'E2EBTC-USDT'})
        out['outside'] = await _call(session, 'export_candles', {'exchange': 'Binance Perpetual Futures',
                                                                 'symbol': 'E2EBTC-USDT', 'path': '/tmp/e2e.csv'})
        out['page_1'] = await _call(session, 'read_project_file', {'path': out['export']['path'], 'max_lines': 3})
        out['preview'] = await _call(session, 'preview_custom_candle_csv', {'symbol': 'E2EBTC-USDT', 'project_path': out['export']['path']})
        out['import'] = await _call(session, 'clean_and_import_custom_candle_csv', {
            'symbol': 'E2EBTC-USDT', 'project_path': out['export']['path'], 'invalid_row_policy': 'reject'})
        out['reimport'] = await _call(session, 'clean_and_import_custom_candle_csv', {
            'symbol': 'E2EBTC-USDT', 'project_path': out['export']['path'], 'invalid_row_policy': 'reject'})
        out['custom_export'] = await _call(session, 'export_candles', {'exchange': 'Custom Data', 'symbol': 'E2EBTC-USDT'})
        out['copy_occupied'] = await _call(session, 'copy_candles', {'exchange': 'Custom Data', 'symbol': 'E2EBTC-USDT',
                                                                     'target_exchange': 'Binance Perpetual Futures'})
        out['copy'] = await _call(session, 'copy_candles', {'exchange': 'Custom Data', 'symbol': 'E2EBTC-USDT',
                                                            'target_exchange': 'Bybit USDT Perpetual'})
        out['delete'] = await _call(session, 'delete_candles', {'exchange': 'Binance Perpetual Futures', 'symbol': 'E2EBTC-USDT'})
        out['purge'] = await _call(session, 'purge_candles', {'exchanges': ['Bybit Spot', 'Hyperliquid Perpetual']})
        out['after'] = await _call(session, 'get_existing_candles', {'symbol': 'e2e'})
        out['window'] = await _call(session, 'get_candles', {'exchange': 'Custom Data', 'symbol': 'E2EBTC-USDT', 'timeframe': '1h'})
        out['bad_import'] = await _call(session, 'import_candles', {'exchange': 'Custom Data', 'symbol': 'E2EBTC-USDT',
                                                                    'start_date': '2024-01-01'})
        out['bad_status'] = await _call(session, 'get_candle_import_status', {'import_id': out['bad_import']['import_id']})
        return out

    out = _mcp(instance, scenario)

    assert {'export_candles', 'purge_candles', 'get_existing_candles', 'copy_candles'} <= out['tools']
    assert [(row['exchange'], row['symbol']) for row in out['inventory']['candle_sets']] == [
        ('Binance Perpetual Futures', 'E2EBTC-USDT'), ('Binance Perpetual Futures', 'E2EETH-USDT'),
        ('Bybit Spot', 'E2EBTC-USDT'), ('Hyperliquid Perpetual', 'E2EX-USDC')]
    assert out['inventory']['candle_sets'][0]['start_date'] == '2024-01-01'
    assert out['inventory']['candle_sets'][0]['end_date'] == '2024-01-09'
    assert [row['symbol'] for row in out['live_only']['candle_sets']] == ['E2EX-USDC']
    assert (out['page']['candle_sets_count'], out['page']['next_offset']) == (2, None)

    export = out['export']
    assert export['status'] == 'success' and export['row_count'] == 12345
    assert export['path'] == 'research_scripts/candle_exports/binance-perpetual-futures_e2ebtc-usdt_1m.csv'
    written = (instance.project / export['path']).read_bytes()
    # The PostgreSQL server-side cursor export equals the dashboard's download, byte for byte.
    assert written == out['dashboard_download']
    assert export['size_bytes'] == len(written)
    assert out['export_again']['error_type'] == 'already_exists'
    assert out['outside']['error_type'] == 'invalid_path' and not Path('/tmp/e2e.csv').exists()
    assert out['page_1']['content'].splitlines()[0] == 'timestamp,open,close,high,low,volume'
    assert out['page_1']['has_more'] is True

    assert out['preview']['cleaning_report']['cleaned_row_count'] == 12345
    assert out['import']['status'] == 'success' and out['import']['symbol'] == 'E2EBTC-USDT'
    assert out['reimport']['status'] == 'success'
    custom = (instance.project / out['custom_export']['path']).read_text().splitlines()
    assert out['custom_export']['row_count'] == 12345 and custom == written.decode().splitlines()

    assert out['copy_occupied']['http_status'] == 409
    assert out['copy']['status'] == 'success' and out['copy']['copied_count'] == 12345
    assert out['delete']['deleted_count'] == 12345 + 100
    assert out['purge']['deleted_count'] == 30 + 10
    assert [(row['exchange'], row['symbol']) for row in out['after']['candle_sets']] == [
        ('Binance Perpetual Futures', 'E2EETH-USDT'), ('Bybit USDT Perpetual', 'E2EBTC-USDT'), ('Custom Data', 'E2EBTC-USDT')]
    assert out['window']['status'] == 'success' and out['window']['candle_count'] == 0, out['window']
    assert out['bad_import']['http_status'] == 422 and 'not a supported historical provider' in out['bad_import']['message']
    assert out['bad_status']['status'] == 'failed'


def test_live_session_management_through_the_mcp_client(instance):
    """
    Drafts, copy, notes, stop, and delete against the real live routes, repository, and Redis
    worker set of a disposable instance. The "running" session is a stored record marked
    active in the instance's own Redis set; nothing starts a session process here.
    """
    strategy = instance.project / 'strategies' / 'E2ELive'
    strategy.mkdir(exist_ok=True)
    (strategy / '__init__.py').write_text(E2E_LIVE_STRATEGY)
    running_id = str(__import__('uuid').uuid4())
    _run_in_instance(instance, RUNNING_SESSION_SCRIPT, running_id)
    active_key = f'{instance.ports["app"]}|active-processes'
    _redis().sadd(active_key, running_id)
    key_id = instance.ids['key']

    async def scenario(session):
        out = {}
        out['paper'] = await _call(session, 'create_live_draft', {
            'paper_mode': True, 'exchange': 'Bybit USDT Perpetual', 'routes': LIVE_ROUTES, 'title': 'E2E paper',
            'config': json.dumps({'exchange': {'balance': 2500}})})
        out['live'] = await _call(session, 'create_live_draft', {
            'paper_mode': False, 'exchange_api_key_id': key_id, 'routes': LIVE_ROUTES})
        out['mismatch'] = await _call(session, 'create_live_draft', {
            'paper_mode': False, 'exchange_api_key_id': key_id, 'exchange': 'Binance Spot', 'routes': LIVE_ROUTES})
        out['bad_routes'] = await _call(session, 'create_live_draft', {
            'paper_mode': True, 'exchange': 'Bybit USDT Perpetual',
            'routes': json.dumps([{'strategy': 'Missing', 'symbol': 'BTC-USDT', 'timeframe': '1h'}])})
        # A secret pasted into a key ID field, with the mode missing or as an object: answered as a
        # normal error result that never quotes it (FastMCP's own errors would).
        out['missing_mode'] = await _call(session, 'create_live_draft', {
            'routes': LIVE_ROUTES, 'exchange_api_key_id': FAKE_API_SECRET})
        out['pasted_key'] = await _call(session, 'create_live_draft', {
            'paper_mode': False, 'routes': LIVE_ROUTES,
            'exchange_api_key_id': {'api_key': FAKE_API_KEY, 'api_secret': FAKE_API_SECRET}})
        paper_id = out['paper']['session_id']
        out['update'] = await _call(session, 'update_live_draft', {'session_id': paper_id, 'debug_mode': False})
        out['summary'] = await _call(session, 'get_session_results', {'session_type': 'live', 'session_id': out['live']['session_id']})
        out['copy'] = await _call(session, 'copy_live_session', {'session_id': running_id, 'title': 'E2E copy'})
        out['notes'] = await _call(session, 'update_live_session_notes', {'session_id': paper_id, 'title': 'E2E renamed'})
        out['stop_draft'] = await _call(session, 'stop_live_session', {'session_id': paper_id})
        out['delete_running'] = await _call(session, 'delete_live_session', {'session_id': running_id})
        out['update_running'] = await _call(session, 'update_live_draft', {'session_id': running_id, 'debug_mode': False})
        out['stop'] = await _call(session, 'stop_live_session', {'session_id': running_id})
        out['after_stop'] = await _call(session, 'get_session_results', {'session_type': 'live', 'session_id': running_id})
        out['delete'] = await _call(session, 'delete_live_session', {'session_id': running_id})
        out['delete_draft'] = await _call(session, 'delete_live_session', {'session_id': out['copy']['session_id']})
        out['listed'] = await _call(session, 'get_live_sessions', {})
        return out

    try:
        out = _mcp(instance, scenario)
        still_active = _redis().sismember(active_key, running_id)
    finally:
        _redis().srem(active_key, running_id)

    paper, live = out['paper'], out['live']
    assert paper['status'] == 'success' and paper['mode'] == 'paper' and paper['config']['exchange']['balance'] == 2500
    assert live['mode'] == 'live' and live['exchange'] == 'Bybit USDT Perpetual'
    assert live['exchange_api_key'] == {'id': key_id, 'name': 'e2e fake key'}
    assert out['mismatch']['error_type'] == 'exchange_mismatch'
    assert out['bad_routes']['error_type'] == 'invalid_routes'
    assert out['missing_mode']['error_type'] == 'invalid_request' and out['pasted_key']['error_type'] == 'invalid_request'
    assert out['update']['debug_mode'] is False
    summary = out['summary']
    assert summary['session_status'] == 'draft' and summary['session_mode'] == 'livetrade'
    assert summary['form']['exchange_api_key_id'] == key_id and summary['form']['paper_mode'] is False
    assert out['copy']['status'] == 'success' and out['copy']['routes'] == json.loads(LIVE_ROUTES)
    assert out['notes']['status'] == 'success'
    assert out['stop_draft']['error_type'] == 'not_running'
    assert out['delete_running']['error_type'] == 'session_active'
    assert out['update_running']['error_type'] == 'not_draft'
    assert out['stop']['status'] == 'success' and out['stop']['mode'] == 'paper'
    assert 'persistency' in out['stop']['on_stop'] and not still_active
    assert out['after_stop']['session_status'] == 'stopped'
    assert out['delete']['status'] == 'success' and out['delete_draft']['status'] == 'success'
    listed_ids = {row['id'] for row in out['listed']['sessions']}
    assert running_id not in listed_ids and out['paper']['session_id'] not in listed_ids  # deleted; drafts are not listed
    text = json.dumps(out)
    worker_log = (instance.project / 'server.log').read_text(errors='replace')
    for secret in (FAKE_API_KEY, FAKE_API_SECRET, FAKE_PASSPHRASE):
        assert secret not in text and secret[-4:] not in text
        assert secret not in worker_log


class _PlanBackend:
    """
    Local stand-in for jesse.trade's /api/v2/user-info (plan and limits) on an instance's
    JESSE_API_URL, recording any unexpected plan preflight requests.
    """

    def __init__(self, port: int) -> None:
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        self.status = 200
        self.limits = {'live_trading_tabs': 1}
        self.requests: list = []
        backend = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                backend.requests.append((self.path, self.headers.get('Authorization')))
                ok = backend.status == 200 and self.headers.get('Authorization') == f'Bearer {FAKE_LICENSE}'
                status = 200 if ok else (backend.status if backend.status != 200 else 401)
                body = {'plan': 'basic', 'limits': backend.limits} if ok else {'message': 'unavailable'}
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *_args):
                pass

        ThreadingHTTPServer.allow_reuse_address = True
        self.server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> '_PlanBackend':
        self.thread.start()
        return self

    def __exit__(self, *_exc) -> None:
        self.server.shutdown()
        self.server.server_close()


def test_invalid_live_starts_are_refused_without_a_plan_preflight(instance):
    """
    A separate instance whose JESSE_API_URL is a local plan stand-in and whose license token is
    fake. Missing-session and dashboard-auth failures never launch a worker or ask for a plan.
    Successful handoff is tested with the recording process manager in test_mcp_live_sessions;
    this real-process integration never starts a trading engine.
    """
    import uuid as uuid_module
    from jesse.mcp.auth import dashboard_token

    project = Path(tempfile.mkdtemp(prefix='jesse-mcp-live-plan-e2e-'))
    (project / 'strategies' / 'E2ELive').mkdir(parents=True)
    (project / 'strategies' / 'E2ELive' / '__init__.py').write_text(E2E_LIVE_STRATEGY)
    (project / 'storage').mkdir()
    password = secrets.token_hex(16)
    token = dashboard_token(password)
    ports = {name: _free_port() for name in ('app', 'lsp', 'api2', 'api1')}
    env_file = _env_file(project, password, ports, {
        'RESET_TEST_DATABASE': 'FALSE', 'LICENSE_API_TOKEN': FAKE_LICENSE,
        'JESSE_API_URL': f'http://127.0.0.1:{ports["api1"]}/api',
    })
    active_key = f'{ports["app"]}|active-processes'

    with _PlanBackend(ports['api1']) as backend:
        process, log = _start(project, _child_env(env_file), with_mcp=True)
        try:
            url = f'http://127.0.0.1:{ports["app"]}'
            _wait_ready(url, password, process, project)
            _wait_for_mcp(url, token, process, project)
            plan_instance = SimpleNamespace(url=url, token=token, project=project, env_file=env_file)

            async def create(session):
                return await _call(session, 'create_live_draft', {
                    'paper_mode': True, 'exchange': 'Bybit USDT Perpetual', 'routes': LIVE_ROUTES})

            draft = _mcp(plan_instance, create)
            assert draft['status'] == 'success'

            async def start(session):
                return await _call(session, 'start_live_session', {'session_id': str(uuid_module.uuid4())})

            backend.status = 503
            unavailable = _mcp(plan_instance, start)

            # Auth runs before body validation, so no valid trading payload is needed here.
            denied = requests.post(f'{url}/live', json={}, timeout=10)

            async def status(session):
                return await _call(session, 'get_session_results', {'session_type': 'live', 'session_id': draft['session_id']})

            after = _mcp(plan_instance, status)
            workers = {member.decode() for member in _redis().smembers(active_key)}
        finally:
            _stop(process, log)
            shutil.rmtree(project, ignore_errors=True)

    assert unavailable['error_type'] == 'not_found'
    assert denied.status_code == 401
    assert after['session_status'] == 'draft' and workers == set()
    assert backend.requests == []
    assert FAKE_LICENSE not in json.dumps([unavailable, after])


# ---------------------------------------------------------------------------
# Live/paper trade and order history by date window
# ---------------------------------------------------------------------------

# Seeds, through the real models, a week of history in a fixed past window that no other test
# writes to: two live sessions (one references the seeded fake key), trades of a deleted
# session, paper, open, discarded, and boundary trades, and groups of three trades closing at
# the same millisecond (one group straddles the snapshot's 1,000-row batch boundary).
HISTORY_SEED = r"""
import json, sys, uuid
from jesse.models.ClosedTrade import ClosedTrade
from jesse.models.Order import Order
from jesse.repositories import live_session_repository

key_id, start, end, fake_key, fake_secret = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4], sys.argv[5]
ids = {name: str(uuid.uuid4()) for name in ('a', 'b', 'deleted', 'paper')}
routes = [{'strategy': 'Demo', 'symbol': 'BTC-USDT', 'timeframe': '1h'}]
live_session_repository.store_live_session(ids['a'], 'stopped', 'livetrade', 'Bybit USDT Perpetual',
    {'form': {'exchange': 'Bybit USDT Perpetual', 'exchange_api_key_id': key_id, 'routes': routes}})
# Recorded as running without a worker: read as stopped, never rewritten by these reads.
live_session_repository.store_live_session(ids['b'], 'running', 'livetrade', 'Bybit USDT Perpetual',
    {'form': {'exchange': 'Bybit USDT Perpetual', 'exchange_api_key_id': '', 'routes': routes}})
live_session_repository.store_live_session(ids['paper'], 'stopped', 'papertrade', 'Bybit USDT Perpetual',
    {'form': {'exchange': 'Bybit USDT Perpetual', 'routes': routes}})
trades, orders = [], []

def trade(session, closed_at, mode='livetrade', symbol='BTC-USDT', soft=None, opened_at=None, exchange_id=None):
    trade_id = str(uuid.uuid4())
    opened = opened_at if opened_at is not None else closed_at - 600000
    trades.append(dict(id=trade_id, session_id=session, strategy_name='Demo', symbol=symbol, exchange='Bybit USDT Perpetual',
                       type='long', timeframe='1h', opened_at=opened, closed_at=closed_at, leverage=1, created_at=opened,
                       updated_at=opened, session_mode=mode, soft_deleted_at=soft))
    legs = [('buy', 100.0, opened, 0.5, None)] + ([('sell', 101.0, closed_at, -0.5, exchange_id)] if closed_at else [])
    for side, price, at, qty, ex in legs:
        orders.append(dict(id=str(uuid.uuid4()), trade_id=trade_id, session_id=session, exchange_id=ex, symbol=symbol,
                           exchange='Bybit USDT Perpetual', side=side, type='MARKET', reduce_only=side == 'sell', qty=qty,
                           filled_qty=qty, price=price, status='EXECUTED', created_at=at, updated_at=at, executed_at=at,
                           session_mode=mode, fee=0.01, vars={}))
    return trade_id

# Closing from 10 minutes after the start, so every entry (10 minutes before its exit) is inside
# the window too: 2,400 orders. Trade 6 belongs to session a (which uses the key), trade 8 to the
# deleted session.
owners = [ids['a'], ids['b'], ids['deleted']]
expected = [trade(owners[i % 3], start + 600000 + (i // 3) * 60000, symbol='ETH-USDT' if i % 5 == 0 else 'BTC-USDT',
                  exchange_id=(f'sig-{fake_secret}' if i == 6 else f'k-{fake_key}' if i == 8 else None)) for i in range(1200)]
trade(ids['paper'], start + 1000, mode='papertrade')
trade(ids['a'], start + 2000, soft=start + 3000)
trade(ids['a'], None, opened_at=start + 4000)
trade(ids['a'], end)
trade(ids['a'], start - 1)
ClosedTrade.insert_many(trades).execute()
for i in range(0, len(orders), 500):
    Order.insert_many(orders[i:i + 500]).execute()
print(json.dumps({**ids, 'expected': expected}))
"""

HISTORY_CODE = """
import json
import matplotlib.pyplot as plt

data = json.load(open("inputs/week.json"))
orders = json.load(open("inputs/orders.json"))
trades = data["trades"]
keys = [(t["closed_at"], t["id"]) for t in trades]
assert keys == sorted(keys) and data["complete"] and data["count"] == len(trades)
print("trades", len(trades), "orders", orders["count"], "open", data["open_trades_not_included"])
print("sessions", sorted((sid, info.get("exists")) for sid, info in data["sessions"].items()))
cumulative, points = 0.0, []
for t in trades:
    cumulative += t["pnl"]
    points.append(cumulative)
print("net", round(cumulative, 6))
stale = json.load(open("inputs/stale.json"))
print("stale session", stale["summary"]["session_status"], stale["complete"], len(stale["closed_trades"]))
fig, ax = plt.subplots(figsize=(8, 4))
ax.plot(points)
ax.set_title("Cumulative pnl of closed live trades (Jesse records)")
fig.savefig("output/week.png", dpi=90)
plt.close(fig)
"""


def test_live_history_by_date_window_through_the_mcp_client(instance):
    from datetime import datetime, timezone
    from PIL import Image
    start_ms = int(datetime(2025, 3, 1, tzinfo=timezone.utc).timestamp() * 1000)
    end_ms = int(datetime(2025, 3, 8, tzinfo=timezone.utc).timestamp() * 1000)
    seeded = json.loads(_run_in_instance(instance, HISTORY_SEED, instance.ids['key'], str(start_ms), str(end_ms),
                                         FAKE_API_KEY, FAKE_API_SECRET).strip().splitlines()[-1])
    window = {'start': '2025-03-01T02:00:00+02:00', 'end': '2025-03-08T00:00:00Z'}  # the same instant as start_ms

    async def scenario(session):
        pages, bounds = [], dict(window)
        while bounds is not None:
            page = await _call(session, 'get_live_trades', {**bounds, 'limit': 500})
            pages.append(page)
            bounds = page['next_page']
        orders_a = await _call(session, 'get_live_orders', {**window, 'session_id': seeded['a'], 'limit': 500,
                                                             'order': 'oldest_first'})
        deleted_orders = await _call(session, 'get_live_orders', {**window, 'session_id': seeded['deleted'],
                                                                   'time_field': 'executed_at', 'limit': 500,
                                                                   'order': 'oldest_first'})
        executed = await _call(session, 'get_live_orders', {**window, 'time_field': 'executed_at', 'status': 'executed',
                                                             'limit': 1})
        paper_recent = await _call(session, 'get_live_trades', {'recent_days': 3, 'mode': 'paper',
                                                                'session_id': instance.ids['live']})
        mismatch = await _call(session, 'get_live_trades', {'recent_days': 3, 'session_id': instance.ids['live']})
        ambiguous = await _call(session, 'get_live_trades', {'start': '2025-03-01'})
        relative_page = await _call(session, 'get_live_trades', {'recent_days': 3, 'cursor': 'eyJ2IjoxfQ'})
        empty = await _call(session, 'get_live_trades', {'start': '2024-01-01T00:00:00Z', 'end': '2024-01-02T00:00:00Z'})
        eth = await _call(session, 'get_live_trades', {**window, 'symbol': 'ETH-USDT', 'limit': 1})
        # A misspelled argument is refused by the worker instead of widening the selection.
        misspelled = await _call(session, 'get_live_trades', {**window, 'symbl': 'ETH-USDT'})

        started = await _call(session, 'run_analysis', {'code': HISTORY_CODE, 'inputs': [
            {'dataset': 'live_trades', 'name': 'week', **window},
            {'dataset': 'live_orders', 'name': 'orders', **window, 'time_field': 'executed_at'},
            # A session recorded as running with no worker: its snapshot runs in a READ ONLY
            # PostgreSQL transaction, so the stale status must be reported without being written.
            {'session_type': 'live', 'session_id': seeded['b'], 'name': 'stale'},
        ]})
        job_id = started['job']['id']
        deadline = time.monotonic() + 120
        while True:
            status = await _call(session, 'get_analysis_job', {'job_id': job_id, 'tail_lines': 50})
            if status['job']['status'] != 'running' or time.monotonic() > deadline:
                break
            await asyncio.sleep(0.5)
        image = await session.call_tool('get_analysis_artifact', {'job_id': job_id, 'path': 'week.png'})
        refused = await _call(session, 'run_analysis', {'code': 'print(1)', 'inputs': [
            {'dataset': 'live_trades', 'name': 'x', **window, 'symbl': 'BTC-USDT'}]})
        return (pages, orders_a, deleted_orders, executed, paper_recent, mismatch, ambiguous, relative_page, empty, eth,
                started, status, image, refused, misspelled)

    (pages, orders_a, deleted_orders, executed, paper_recent, mismatch, ambiguous, relative_page, empty, eth,
     started, status, image, refused, misspelled) = _mcp(instance, scenario)
    assert misspelled['error_type'] == 'invalid_request' and 'accepts only' in misspelled['message']
    headers = {'Authorization': _hash(instance.password)}
    route_extra = requests.post(f'{instance.url}/session-results/live-trades', headers=headers, timeout=30,
                                json={**window, 'symbl': 'ETH-USDT'})
    assert route_extra.status_code == 400 and route_extra.json()['error_type'] == 'invalid_request'
    # An offset that moves a value past the calendar's end is refused, not a server error.
    edge = requests.post(f'{instance.url}/session-results/live-trades', headers=headers, timeout=30,
                         json={'start': '9999-12-31T23:59:59-00:01'})
    assert edge.status_code == 400 and edge.json()['error_type'] == 'invalid_request'

    # Every live trade closed in [start, end) exactly once, newest first, ties ordered by id; the
    # paper, discarded, open, and out-of-window trades are not among them.
    first = pages[0]
    assert (first['range']['start_ms'], first['range']['end_ms']) == (start_ms, end_ms)
    assert first['total'] == 1200 and first['all_records_returned'] is False and len(pages) > 2
    assert all(page['truncated_by_size'] for page in pages[:-1])  # 128 KiB per page, fewer than 500 trades
    items = [item for page in pages for item in page['items']]
    assert len(items) == 1200 and {item['id'] for item in items} == set(seeded['expected'])
    assert [(item['closed_at'], item['id']) for item in items] == sorted(
        ((item['closed_at'], item['id']) for item in items), reverse=True)
    assert first['open_trades_not_included'] == 1
    sessions = {sid: info for page in pages for sid, info in page['sessions'].items()}
    assert sessions[seeded['a']]['status'] == 'stopped' and sessions[seeded['b']]['status'] == 'stopped'
    assert sessions[seeded['deleted']] == {'exists': False} and seeded['paper'] not in sessions

    # Redaction per record: the fake key's values in an order of the session using it and in an
    # order of a deleted session; nothing unredacted anywhere.
    assert any(order['exchange_id'] == 'sig-[redacted]' for order in orders_a['items'])
    assert any(order['exchange_id'] == 'k-[redacted]' for order in deleted_orders['items'])
    # 2,400 orders of the expected trades, plus three executed inside the window: the discarded
    # trade's exit, the open trade's entry, and the entry of the trade closing at the end.
    assert executed['total'] == 2403 and executed['counts_by_status'] == {'EXECUTED': 2403}
    assert paper_recent['total'] == 25 and {item['session_mode'] for item in paper_recent['items']} == {'papertrade'}
    assert mismatch['error_type'] == 'mode_mismatch'
    assert ambiguous['error_type'] == 'invalid_request' and relative_page['error_type'] == 'invalid_request'
    assert (empty['total'], empty['items'], empty['all_records_returned']) == (0, [], True)
    assert eth['total'] == 240
    # Reading never rewrote the stale "running" record.
    assert 'running' in _run_in_instance(instance, 'import sys\nfrom jesse.models.LiveSession import LiveSession\n'
                                         'print(LiveSession.get(LiveSession.id == sys.argv[1]).status)', seeded['b'])

    # The analysis snapshot is the complete selection (two 1,000-row batches), charted and returned as an image.
    entries = {entry['name']: entry for entry in started['job']['inputs']}
    assert (entries['week']['count'], entries['orders']['count']) == (1200, 2403)
    assert entries['week']['range']['start_ms'] == start_ms and entries['orders']['filters']['time_field'] == 'executed_at'
    assert status['job']['status'] == 'succeeded', status['output']
    assert 'trades 1200 orders 2403 open 1' in status['output']
    assert 'stale session stopped True 400' in status['output'], status['output']
    assert f"('{seeded['deleted']}', False)" in status['output']
    assert not image.isError and [c.type for c in image.content] == ['text', 'image']
    with Image.open(io.BytesIO(base64.b64decode(image.content[1].data))) as decoded:
        assert decoded.format == 'PNG'
    workspace = instance.project / 'storage' / 'mcp' / 'analysis' / started['job']['id'] / 'inputs'
    for name in ('week.json', 'orders.json', 'manifest.json'):
        text = (workspace / name).read_text()
        assert FAKE_API_KEY not in text and FAKE_API_SECRET not in text and FAKE_PASSPHRASE not in text
    assert refused['error_type'] == 'invalid_request'  # the misspelled filter is refused, not ignored
    everything = json.dumps([pages, orders_a, deleted_orders, executed, started, status])
    assert FAKE_API_KEY not in everything and FAKE_API_SECRET not in everything


# Seeds, in a past window no other test uses, 20,000 ACTIVE orders on one exchange, and on a
# second exchange one closed trade with 10,001 executed orders (over the per-trade limit).
CONSISTENCY_SEED = r"""
import json, sys, uuid
from jesse.models.ClosedTrade import ClosedTrade
from jesse.models.Order import Order
from jesse.repositories import live_session_repository

start, flip_exchange, heavy_exchange = int(sys.argv[1]), sys.argv[2], sys.argv[3]
session = str(uuid.uuid4())
live_session_repository.store_live_session(session, 'stopped', 'livetrade', flip_exchange,
    {'form': {'exchange': flip_exchange, 'exchange_api_key_id': '', 'routes': []}})

def order(at, trade_id=None, exchange=flip_exchange, status='ACTIVE', side='buy', qty=1.0):
    return dict(id=str(uuid.uuid4()), trade_id=trade_id, session_id=session, symbol='BTC-USDT', exchange=exchange,
                side=side, type='LIMIT', reduce_only=False, qty=qty, filled_qty=qty if status == 'EXECUTED' else 0,
                price=100.0, status=status, created_at=at, updated_at=at, executed_at=at if status == 'EXECUTED' else None,
                session_mode='livetrade', vars={})

rows = [order(start + i) for i in range(20000)]
heavy = str(uuid.uuid4())
ClosedTrade.insert(id=heavy, session_id=session, strategy_name='Demo', symbol='BTC-USDT', exchange=heavy_exchange,
                   type='long', timeframe='1m', opened_at=start, closed_at=start + 3600000, leverage=1, created_at=start,
                   updated_at=start, session_mode='livetrade').execute()
rows += [order(start + i, heavy, heavy_exchange, 'EXECUTED') for i in range(10000)]
rows.append(order(start + 3600000, heavy, heavy_exchange, 'EXECUTED', 'sell', -10000.0))
for i in range(0, len(rows), 1000):
    Order.insert_many(rows[i:i + 1000]).execute()
print(json.dumps({'session': session, 'heavy': heavy}))
"""

CONSISTENCY_CODE = """
import json
data = json.load(open("inputs/orders.json"))
statuses = sorted({row["status"] for row in data["orders"]})
print("statuses", statuses, "counts", data["counts_by_status"], "count", data["count"])
"""


def _postgres_connection():
    """An independent PostgreSQL connection to the instance's disposable schema, like a session process."""
    import psycopg2
    return psycopg2.connect(
        host=os.environ.get('JESSE_MCP_INTEGRATION_POSTGRES_HOST', '127.0.0.1'),
        port=int(os.environ.get('JESSE_MCP_INTEGRATION_POSTGRES_PORT', '5432')),
        dbname=os.environ.get('JESSE_MCP_INTEGRATION_POSTGRES_NAME', 'jesse_db'),
        user=os.environ.get('JESSE_MCP_INTEGRATION_POSTGRES_USERNAME', 'jesse_user'),
        password=os.environ.get('JESSE_MCP_INTEGRATION_POSTGRES_PASSWORD', 'password'),
        options=f'-c search_path={SCHEMA}',
    )


def test_history_reads_one_postgres_snapshot_while_an_independent_writer_commits(instance):
    import threading
    from datetime import datetime, timezone
    start_ms = int(datetime(2025, 5, 1, tzinfo=timezone.utc).timestamp() * 1000)
    flip_exchange, heavy_exchange = 'E2E Consistency Exchange', 'E2E Heavy Exchange'
    seeded = json.loads(_run_in_instance(instance, CONSISTENCY_SEED, str(start_ms), flip_exchange,
                                         heavy_exchange).strip().splitlines()[-1])
    window = {'start': '2025-05-01T00:00:00Z', 'end': '2025-05-02T00:00:00Z'}

    # The writer flips all 20,000 orders between ACTIVE and CANCELED in one transaction at a time,
    # so every committed state has a single status; a reader mixing views would see both.
    stop, flips, failures = threading.Event(), [], []

    def writer():
        connection = _postgres_connection()
        try:
            with connection.cursor() as cursor:
                while not stop.is_set():
                    cursor.execute('UPDATE "order" SET status = CASE WHEN status = %s THEN %s ELSE %s END '
                                   'WHERE exchange = %s', ('ACTIVE', 'CANCELED', 'ACTIVE', flip_exchange))
                    connection.commit()
                    flips.append(time.monotonic())
        except Exception as exc:  # reported below
            failures.append(exc)
        finally:
            connection.close()

    thread = threading.Thread(target=writer)
    thread.start()

    async def scenario(session):
        pages = [await _call(session, 'get_live_orders', {**window, 'exchange': flip_exchange, 'limit': 500})]
        for _ in range(3):
            pages.append(await _call(session, 'get_live_orders', pages[-1]['next_page']))
        began = len(flips)
        started = await _call(session, 'run_analysis', {'code': CONSISTENCY_CODE, 'inputs': [
            {'dataset': 'live_orders', 'name': 'orders', **window, 'exchange': flip_exchange}]})
        during = len(flips) - began
        deadline = time.monotonic() + 120
        while True:
            status = await _call(session, 'get_analysis_job', {'job_id': started['job']['id']})
            if status['job']['status'] != 'running' or time.monotonic() > deadline:
                break
            await asyncio.sleep(0.3)
        heavy_page = await _call(session, 'get_live_trades', {**window, 'exchange': heavy_exchange})
        heavy_snapshot = await _call(session, 'run_analysis', {'code': 'print(1)', 'inputs': [
            {'dataset': 'live_trades', **window, 'exchange': heavy_exchange}]})
        return pages, started, during, status, heavy_page, heavy_snapshot

    try:
        pages, started, during, status, heavy_page, heavy_snapshot = _mcp(instance, scenario)
    finally:
        stop.set()
        thread.join(30)
    assert not failures and len(flips) >= 2

    # Every page, and the whole snapshot, is one committed state: one status, counted consistently.
    for page in pages:
        [page_status] = {item['status'] for item in page['items']}
        assert page['counts_by_status'] == {page_status: 20000} and page['total'] == 20000
    assert status['job']['status'] == 'succeeded', status['output']
    assert re.search(r"statuses \['(ACTIVE|CANCELED)'\] counts \{'\1': 20000\} count 20000", status['output']), status['output']
    assert started['job']['inputs'][0]['count'] == 20000
    # The writer kept committing while the snapshot was read: the read transaction blocks nobody.
    assert during >= 1

    # A trade over the per-trade order limit is refused, never computed from part of its orders.
    assert heavy_page['error_type'] == 'too_many_orders' and seeded['heavy'] in heavy_page['message']
    assert heavy_snapshot['error_type'] == 'too_many_orders'
    # No history read left a transaction open on the instance's connections (refusals included).
    connection = _postgres_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM pg_stat_activity WHERE state LIKE 'idle in transaction%%' "
                           "AND (query LIKE %s OR query LIKE %s)", (f'%{flip_exchange}%', f'%{heavy_exchange}%'))
            assert cursor.fetchone()[0] == 0
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# The documented "analyze my trades" workflow through the SDK client
# ---------------------------------------------------------------------------

# Recent closed trades (relative to now) on one exchange no other test uses: live trades in three
# quote currencies across two sessions, one without an exit leg (no pnl), one without a recorded
# fee, and paper trades.
WORKFLOW_SEED = r"""
import json, sys, uuid
import jesse.helpers as jh
from jesse.models.ClosedTrade import ClosedTrade
from jesse.models.Order import Order
from jesse.repositories import live_session_repository

exchange = sys.argv[1]
now = jh.now_to_timestamp(True)
day = 86400000
ids = {name: str(uuid.uuid4()) for name in ('live', 'live2', 'paper')}
for name, mode in (('live', 'livetrade'), ('live2', 'livetrade'), ('paper', 'papertrade')):
    live_session_repository.store_live_session(ids[name], 'stopped', mode, exchange,
        {'form': {'exchange': exchange, 'exchange_api_key_id': '', 'routes': []}})
trades, orders, made = [], [], {}

def trade(label, session, symbol, days_ago, entry, exit, qty, mode='livetrade', exit_leg=True, fees=(0.01, 0.01)):
    trade_id = str(uuid.uuid4())
    closed = now - int(days_ago * day)
    opened = closed - 600000
    trades.append(dict(id=trade_id, session_id=ids[session], strategy_name='Demo', symbol=symbol, exchange=exchange,
                       type='long', timeframe='1h', opened_at=opened, closed_at=closed, leverage=1, created_at=opened,
                       updated_at=closed, session_mode=mode))
    legs = [('buy', entry, opened, qty, fees[0])] + ([('sell', exit, closed, -qty, fees[1])] if exit_leg else [])
    for side, price, at, amount, fee in legs:
        orders.append(dict(id=str(uuid.uuid4()), trade_id=trade_id, session_id=ids[session], symbol=symbol, exchange=exchange,
                           side=side, type='MARKET', reduce_only=side == 'sell', qty=amount, filled_qty=amount, price=price,
                           status='EXECUTED', created_at=at, updated_at=at, executed_at=at, session_mode=mode, fee=fee, vars={}))
    made[label] = trade_id

trade('btc_win', 'live', 'BTC-USDT', 1, 100.0, 112.5, 2.0)
trade('btc_loss', 'live', 'BTC-USDT', 2, 110.0, 104.0, 1.0)
trade('eth_btc', 'live', 'ETH-BTC', 2.5, 0.05, 0.0512345, 0.3, fees=(0.000001, 0.000002))
trade('aapl_no_exit', 'live', 'AAPL-USD', 5, 200.0, 0.0, 1.0, exit_leg=False)
trade('sol_no_fee', 'live2', 'SOL-USDT', 6, 20.0, 21.5, 4.0, fees=(0.1, None))
trade('paper_1', 'paper', 'BTC-USDT', 1, 100.0, 90.0, 1.0, mode='papertrade')
trade('paper_4', 'paper', 'BTC-USDT', 4, 90.0, 99.0, 1.0, mode='papertrade')
ClosedTrade.insert_many(trades).execute()
Order.insert_many(orders).execute()
print(json.dumps({**ids, 'trades': made}))
"""


def _workflow_groups(output: str) -> dict:
    groups: dict = {}
    current = None
    for line in output.splitlines():
        if line.startswith('group '):
            current = line
            groups[current] = []
        elif line.startswith('  ') and current:
            groups[current].append(line.strip())
    return groups


def _expected_workflow_groups(items: list) -> dict:
    """What the documented code must print for these discovery items, derived independently."""
    import math
    grouped: dict = {}
    for item in sorted(items, key=lambda i: (i['closed_at'], i['id'])):
        parts = item['symbol'].split('-')
        quote = parts[1] if len(parts) == 2 and all(parts) else None
        grouped.setdefault((item['session_mode'], quote), []).append(item)
    expected = {}
    for (mode, quote), trades in grouped.items():
        unknown = sum(1 for t in trades if t['pnl'] is None)
        missing = sum(1 for t in trades if t['orders_without_fee'] > 0)
        header = (f'group mode={mode} quote={quote or "unknown"} trades={len(trades)} unknown_pnl={unknown} '
                  f'missing_fee_trades={missing}')
        if quote is None:
            expected[header] = ['not computed: the symbol is not BASE-QUOTE, so the pnl currency is unknown']
        elif unknown:
            expected[header] = [f'not computed: {unknown} of {len(trades)} trades have no pnl']
        else:
            pnls = [t['pnl'] for t in trades]
            expected[header] = [f'net_closed_trade_pnl={math.fsum(pnls)!r} {quote} wins={sum(1 for p in pnls if p > 0)}/{len(pnls)}',
                                f'chart output/cumulative_pnl_{mode}_{quote}.png']
    return expected


def test_the_documented_trade_analysis_workflow_through_the_mcp_client(instance):
    exchange = 'E2E Workflow Exchange'
    seeded = json.loads(_run_in_instance(instance, WORKFLOW_SEED, exchange).strip().splitlines()[-1])
    made = seeded['trades']

    async def scenario(session):
        guide = (await session.read_resource('jesse://session_analysis')).contents[0].text
        workflow = guide[guide.index('### Workflow: "analyze my trades of the last 7 days"'):]
        code = workflow.split('```python\n', 1)[1].split('\n```', 1)[0] + '\n'
        jobs_before = await _call(session, 'get_analysis_job', {})
        runs = {}
        for label, arguments in (
            ('last_3_days', {'recent_days': 3, 'exchange': exchange}),
            ('last_7_days', {'recent_days': 7, 'exchange': exchange}),
            ('default', {}),
            ('exact', {'exchange': exchange, 'symbol': 'BTC-USDT', 'session_id': seeded['live']}),
            ('paper', {'mode': 'paper', 'exchange': exchange}),
            ('empty', {'exchange': exchange, 'start': '2024-01-01T00:00:00Z', 'end': '2024-01-08T00:00:00Z'}),
        ):
            discovery = await _call(session, 'get_live_trades', {**arguments, 'limit': 500})
            run = {'discovery': discovery}
            if discovery['total']:
                # Step 2 as documented: the returned range and every non-null filter except session_modes.
                request = {'dataset': 'live_trades', 'name': 'trades', 'start': discovery['range']['start'],
                           'end': discovery['range']['end'],
                           **{k: v for k, v in discovery['filters'].items() if k != 'session_modes' and v is not None}}
                started = await _call(session, 'run_analysis', {'code': code, 'inputs': [request]})
                deadline = time.monotonic() + 120
                while True:
                    status = await _call(session, 'get_analysis_job', {'job_id': started['job']['id'], 'tail_lines': 200})
                    if status['job']['status'] != 'running' or time.monotonic() > deadline:
                        break
                    await asyncio.sleep(0.3)
                images = {}
                for artifact in status['artifacts']:
                    images[artifact['path']] = await session.call_tool(
                        'get_analysis_artifact', {'job_id': started['job']['id'], 'path': artifact['path']})
                run.update(request=request, started=started, status=status, images=images)
            runs[label] = run
        jobs_after = await _call(session, 'get_analysis_job', {})
        return runs, jobs_before, jobs_after

    runs, jobs_before, jobs_after = _mcp(instance, scenario)

    expected_ids = {
        'last_3_days': {made['btc_win'], made['btc_loss'], made['eth_btc']},
        'last_7_days': {made['btc_win'], made['btc_loss'], made['eth_btc'], made['aapl_no_exit'], made['sol_no_fee']},
        'default': {made['btc_win'], made['btc_loss'], made['eth_btc'], made['aapl_no_exit'], made['sol_no_fee']},
        'exact': {made['btc_win'], made['btc_loss']},
        'paper': {made['paper_1'], made['paper_4']},
    }
    for label, ids in expected_ids.items():
        run = runs[label]
        discovery, status, manifest = run['discovery'], run['status'], run['started']['job']['inputs'][0]
        assert {item['id'] for item in discovery['items']} == ids and discovery['all_records_returned'], label
        assert 'session_modes' not in run['request'] and run['request']['mode'] == discovery['filters']['mode']
        # The snapshot is the same selection: the manifest repeats the bounds and filters (its range
        # "source" is start_end, as it was given the discovery's explicit bounds), and its count.
        bounds = ('start', 'end', 'start_ms', 'end_ms')
        assert [manifest['range'][key] for key in bounds] == [discovery['range'][key] for key in bounds], label
        assert (manifest['filters'], manifest['count']) == (discovery['filters'], discovery['total']), label
        assert status['job']['status'] == 'succeeded', status['output']
        assert _workflow_groups(status['output']) == _expected_workflow_groups(discovery['items']), (label, status['output'])
        charts = {line.split('output/', 1)[1] for lines in _workflow_groups(status['output']).values()
                  for line in lines if line.startswith('chart ')}
        assert set(run['images']) == charts, label
        for image in run['images'].values():
            assert not image.isError and [c.type for c in image.content] == ['text', 'image']
            assert base64.b64decode(image.content[1].data).startswith(b'\x89PNG')
    # The unknown pnl and missing fee are disclosed, and the null-pnl USD group has no total or chart.
    last_week = _workflow_groups(runs['last_7_days']['status']['output'])
    assert last_week['group mode=livetrade quote=USD trades=1 unknown_pnl=1 missing_fee_trades=0'] == [
        'not computed: 1 of 1 trades have no pnl']
    assert any('missing_fee_trades=1' in header for header in last_week)
    assert runs['default']['discovery']['filters']['exchange'] is None  # nothing added to the default selection
    # Empty discovery: the workflow stops, so no analysis job was created for it.
    assert runs['empty']['discovery']['total'] == 0 and 'started' not in runs['empty']
    assert len(jobs_after['jobs']) == len(jobs_before['jobs']) + 5
