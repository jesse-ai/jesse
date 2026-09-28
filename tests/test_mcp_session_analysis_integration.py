"""
End-to-end proof of session results and temporary analysis on a disposable Jesse instance.

Starts `jesse run` from a throwaway project with its own env file, a guarded test schema
(`mcp_analysis_e2e_test`, dropped and recreated at startup exactly like the dashboard E2E
stack), its own ports, and its own Redis DB. Real records are written into that schema with
Jesse's own model functions, then an MCP SDK client connects through the dashboard's
authenticated /mcp route and exercises the tools: results of every session type, a real
matplotlib analysis over snapshots, the chart as MCP image content, and earlier tools,
including a metered run whose usage check waits on a local stand-in for the licensing backend.
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
    return json.loads(result.content[0].text)


def test_authentication_is_required_everywhere(instance):
    import requests
    for route in ('/session-results/get', '/session-results/live-sessions', '/analysis/run', '/analysis/artifact'):
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
    assert len(first['tools'].tools) == 90
    assert first['run'] == {'status': 'error', 'message': f'Session {missing} not found'}

    assert second['reply']['error']['message'] == 'Request cancelled' and second['reply_seconds'] < 3
    assert len(second['listed']['result']['tools']) == 90
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
        assert first == second and first[0] == 90 and first[1] > 100

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
