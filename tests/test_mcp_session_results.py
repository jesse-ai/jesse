"""
Session results: bounded summaries and pages of stored backtest, optimization, Monte Carlo,
significance-test, and live/paper sessions, through the real routes and MCP tools.

The database is replaced by stored-record stand-ins that have the same columns (JSON text
where Jesse stores JSON text), so these tests run without PostgreSQL. The disposable-instance
integration test (test_mcp_session_analysis_integration.py) covers the real database.
"""
import contextlib
import json
import math
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import jesse.mcp.tools.services.project_files as project_files_service
from jesse.controllers import session_results_controller
from jesse.mcp.tools import register_tools
from jesse.services import auth, session_results
from tests.mcp_tool_adapters import callable_tool


PASSWORD = 'session-results-password'
HEADERS = {'Authorization': sha256(PASSWORD.encode('utf-8')).hexdigest()}
BACKTEST_ID = '11111111-1111-4111-8111-111111111111'
OPTIMIZATION_ID = '22222222-2222-4222-8222-222222222222'
MONTE_CARLO_ID = '33333333-3333-4333-8333-333333333333'
SIGNIFICANCE_ID = '44444444-4444-4444-8444-444444444444'
LIVE_ID = '55555555-5555-4555-8555-555555555555'
API_KEY = 'LIVEKEY-abcdef123456'
API_SECRET = 'LIVESECRET-zyxwvu987654'
PASSPHRASE = 'passphrase-42424242'

FORM = {'exchange': 'Binance Perpetual Futures', 'routes': [{'strategy': 'Demo', 'symbol': 'BTC-USDT', 'timeframe': '4h'}],
        'data_routes': [], 'start_date': '2025-01-01', 'finish_date': '2025-06-01'}
METRICS = {'total': 3, 'net_profit_percentage': 12.5, 'max_drawdown': -4.2, 'sharpe_ratio': 1.4,
           'win_rate': 0.66, 'serenity_index': float('nan'), 'omega_ratio': float('inf')}


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorator(func):
            self.tools[func.__name__] = callable_tool(func)
            return func
        return decorator

    def resource(self, uri):
        return lambda func: func


def _trade(i: int) -> dict:
    return {'id': f'trade-{i}', 'symbol': 'BTC-USDT', 'type': 'long' if i % 2 else 'short', 'entry_price': 100.0 + i,
            'exit_price': 101.0 + i, 'qty': 1.0, 'opened_at': 1735689600000 + i * 3_600_000,
            'closed_at': 1735693200000 + i * 3_600_000, 'PNL': float(i), 'PNL_percentage': i / 10, 'orders': []}


def _curve(name: str, points: int) -> dict:
    return {'name': name, 'color': '#818CF8',
            'data': [{'time': 1735689600 + d * 86400, 'value': 10_000 + d} for d in range(points)]}


def _backtest_row(**overrides):
    values = dict(
        id=BACKTEST_ID, status='finished', title='MCP Backtest: Demo', description='notes',
        created_at=1, updated_at=2, execution_duration=3.5,
        state=json.dumps({'form': FORM}), metrics=json.dumps(METRICS, allow_nan=True),
        trades=json.dumps([_trade(i) for i in range(7)]),
        equity_curve=json.dumps([_curve('Portfolio', 30), _curve('BTC-USDT', 30)]),
        hyperparameters=json.dumps([['fast', 10], ['slow', 30]]),
        chart_data=None, exception=None, traceback=None,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _trial(rank: int) -> dict:
    metrics = {'net_profit_percentage': 10.0 - rank, 'max_drawdown': -5.0, 'sharpe_ratio': 2.0 - rank / 10,
               'win_rate': 0.5, 'total': 20, 'calmar_ratio': 1.1}
    return {'trial': 100 + rank, 'params': {'fast': rank}, 'fitness': 1 / (rank + 1), 'dna': f'dna{rank}',
            'training_metrics': metrics, 'testing_metrics': metrics}


def _optimization_row():
    return SimpleNamespace(
        id=OPTIMIZATION_ID, status='finished', completed_trials=40, total_trials=40, created_at=1, updated_at=2,
        best_score=0.9, best_trials=json.dumps([_trial(r) for r in range(5)]), objective_curve=json.dumps([0.1, 0.2, 0.3]),
        state_json={'form': {**FORM, 'objective_function': 'sharpe'}}, exception=None, traceback=None,
        title='opt', description=None, strategy_codes=None,
    )


def _mc_results(scenarios: int) -> dict:
    def backtest(index):
        return {'scenario_index': index, 'metrics': {'sharpe_ratio': 1.0 + index / 100}, 'equity_curve': [_curve('Portfolio', 5)],
                'trades': [_trade(0)]}
    ca = {'metrics': {'sharpe_ratio': {'original': 1.2, 'percentiles': {'5th': 0.4, '50th': 1.0, '95th': 1.6}}}, 'summary': {}}
    return {'original': backtest(0), 'scenarios': [backtest(i + 1) for i in range(scenarios)], 'confidence_analysis': ca,
            'num_scenarios': scenarios, 'total_requested': scenarios}


def _monte_carlo_row(with_results: bool = True):
    results = _mc_results(4)
    candles = SimpleNamespace(
        id='c', status='finished', num_scenarios=4, completed_scenarios=4, pipeline_type='gaussian_noise',
        pipeline_params=json.dumps({'batch_size': 7}), results=json.dumps(results) if with_results else None,
        results_json=results, logs='first\nsecond\n', exception=None, traceback=None,
    )
    return SimpleNamespace(id=MONTE_CARLO_ID, status='finished', created_at=1, updated_at=2, title='mc', description=None,
                           state_json={'form': FORM}, trades_session=None, candles_session=candles)


def _significance_row(project: Path):
    chart = project / 'storage' / 'significance-test-charts' / 'chart.png'
    chart.parent.mkdir(parents=True, exist_ok=True)
    chart.write_bytes(b'png')
    return SimpleNamespace(
        id=SIGNIFICANCE_ID, status='finished', title='rst', description=None, created_at=1, updated_at=2,
        state=json.dumps({'form': FORM}), chart_path=str(chart), exception=None, traceback=None,
        results=json.dumps({'p_value': 0.03, 'observed_mean': 0.001, 'annualized_return': 0.2,
                            'n_simulations': 2000, 'n_observations': 150}),
    )


@pytest.fixture
def project(tmp_path, monkeypatch) -> Path:
    root = tmp_path / 'project'
    (root / 'storage').mkdir(parents=True)
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def stored(project, monkeypatch):
    """Stored records keyed by session type; tests may replace entries."""
    records = {
        'backtest': {BACKTEST_ID: _backtest_row()},
        'optimization': {OPTIMIZATION_ID: _optimization_row()},
        'monte_carlo': {MONTE_CARLO_ID: _monte_carlo_row()},
        'significance_test': {SIGNIFICANCE_ID: _significance_row(project)},
    }
    monkeypatch.setattr(session_results, '_load_backtest', lambda i: records['backtest'].get(i))
    monkeypatch.setattr(session_results, '_load_optimization', lambda i: records['optimization'].get(i))
    monkeypatch.setattr(session_results, '_load_monte_carlo', lambda i: records['monte_carlo'].get(i))
    monkeypatch.setattr(session_results, '_load_significance_test', lambda i: records['significance_test'].get(i))
    return records


class FakeLive:
    """A live session's rows as the live plugin stores them (trades, orders, equity, logs)."""

    def __init__(self):
        self.view = {
            'id': LIVE_ID, 'status': 'stopped', 'is_active': False, 'session_mode': 'papertrade',
            'exchange': 'Bybit USDT Perpetual', 'created_at': 1, 'updated_at': 2, 'finished_at': 3,
            'state': {'form': {**FORM, 'exchange_api_key_id': 'key-id', 'notification_api_key_id': None}},
            'title': 'paper run', 'description': None,
            'exception': f'AuthError: key {API_KEY} rejected',
            'traceback': f'Traceback...\nrequest signed with {API_SECRET}\n',
        }
        self.trades = [{'id': f't{i}', 'symbol': 'BTC-USDT', 'pnl': float(i), 'opened_at': i, 'status': 'closed'} for i in range(12)]
        self.orders = [{'id': f'o{i}', 'side': 'buy', 'status': 'EXECUTED'} for i in range(5)]
        self.equity = [{'time': 60_000 * i, 'equity': 1000.0 + i, 'currency': 'USDT'} for i in range(9)]
        # Newest first, as the database query returns them.
        self.logs = {1: [{'timestamp': 100 - i, 'message': f'info {99 - i}'} for i in range(100)],
                     2: [{'timestamp': 5, 'message': f'order failed: passphrase {PASSPHRASE} invalid'}]}
        self.secrets_requested_with = None
        # The stored row: redaction reads its raw state column, like the real LiveSession.
        self.row = SimpleNamespace(id=LIVE_ID, state=json.dumps(self.view['state']))

    def install(self, monkeypatch):
        monkeypatch.setattr(session_results, '_live_plugin_available', lambda: True)
        monkeypatch.setattr(session_results, '_load_live', lambda i: self.row if i == LIVE_ID else None)
        monkeypatch.setattr(session_results, '_live_session_view', lambda row, *_: json.loads(json.dumps(self.view)))
        # Stored-record stand-ins have no database whose transaction could hold a snapshot.
        monkeypatch.setattr(session_results, '_read_snapshot', contextlib.nullcontext)
        monkeypatch.setattr(session_results, '_live_trades', self._page(self.trades))
        monkeypatch.setattr(session_results, '_live_orders', self._page(self.orders))
        monkeypatch.setattr(session_results, '_live_equity', self._page(self.equity))
        monkeypatch.setattr(session_results, '_live_logs',
                            lambda _id, kind, offset, limit: (self.logs[kind][offset:offset + limit], len(self.logs[kind])))
        monkeypatch.setattr(session_results, '_live_counts', lambda _id: {'trades': len(self.trades), 'orders': len(self.orders)})
        monkeypatch.setattr(session_results, '_live_secrets', self._secrets)
        monkeypatch.setattr(session_results, '_list_live_rows', lambda *args: [self.row])
        return self

    def _page(self, rows):
        return lambda _id, offset, limit: (rows[offset:offset + limit] if limit is not None else rows[offset:], len(rows))

    def _secrets(self, form):
        self.secrets_requested_with = form
        return [API_SECRET, API_KEY, PASSPHRASE]


@pytest.fixture
def live(stored, monkeypatch) -> FakeLive:
    return FakeLive().install(monkeypatch)


@pytest.fixture
def api(monkeypatch) -> TestClient:
    monkeypatch.setitem(auth.ENV_VALUES, 'PASSWORD', PASSWORD)
    app = FastAPI()

    @app.exception_handler(auth.InvalidAuthError)
    async def invalid_auth_handler(_request, _exc):
        return auth.unauthorized_response()

    app.include_router(session_results_controller.router)
    return TestClient(app)


def _get(api, session_type, session_id, section='summary', offset=0, limit=50, expect=200) -> dict:
    response = api.post('/session-results/get', headers=HEADERS, json={
        'session_type': session_type, 'session_id': session_id, 'section': section, 'offset': offset, 'limit': limit})
    assert response.status_code == expect, response.text
    return response.json()


def _refused(api, error_type, status_code, **payload) -> dict:
    body = _get(api, payload.pop('session_type', 'backtest'), payload.pop('session_id', BACKTEST_ID), expect=status_code, **payload)
    assert (body['status'], body['error_type']) == ('error', error_type), body
    return body


# ---------------------------------------------------------------------------
# Authentication and validation
# ---------------------------------------------------------------------------

def test_routes_require_authentication(api, stored):
    for route, payload in (('get', {'session_type': 'backtest', 'session_id': BACKTEST_ID}), ('live-sessions', {})):
        response = api.post(f'/session-results/{route}', json=payload, headers={'Authorization': 'wrong'})
        assert response.status_code == 401


@pytest.mark.parametrize('payload', [
    {'session_type': 'paper'},
    {'session_id': 'not-a-uuid'},
    {'section': 'metrics'},
    {'session_type': 'significance_test', 'session_id': SIGNIFICANCE_ID, 'section': 'trades'},
    {'offset': -1},
    {'limit': 0},
    {'limit': session_results.MAX_LIMIT + 1},
])
def test_invalid_requests_are_refused_before_reading(api, stored, monkeypatch, payload):
    monkeypatch.setattr(session_results, '_load_backtest', lambda _id: pytest.fail('read before validation'))
    body = _refused(api, 'invalid_request', 400, **payload)
    assert body['message']


def test_unknown_sessions_are_not_found(api, stored):
    for session_type in ('backtest', 'optimization', 'monte_carlo', 'significance_test'):
        body = _refused(api, 'not_found', 404, session_type=session_type, session_id='99999999-9999-4999-8999-999999999999')
        assert 'does not exist' in body['message']


def test_unexpected_read_failures_are_reported_without_details(api, stored, monkeypatch):
    def broken(_id):
        raise RuntimeError('connection to server at "db" failed: password=hunter2')

    monkeypatch.setattr(session_results, '_load_backtest', broken)
    body = _refused(api, 'read_failed', 500)
    assert 'RuntimeError' in body['message'] and 'hunter2' not in json.dumps(body)


# ---------------------------------------------------------------------------
# Backtests
# ---------------------------------------------------------------------------

def test_backtest_summary_is_compact_and_describes_the_sections(api, stored, project):
    log = project / 'storage' / 'logs' / 'backtest-mode' / f'{BACKTEST_ID}.txt'
    log.parent.mkdir(parents=True)
    log.write_text('a\nb\n')

    summary = _get(api, 'backtest', BACKTEST_ID)

    assert summary['status'] == 'success' and summary['session_type'] == 'backtest'
    assert summary['session_status'] == 'finished'
    assert summary['form'] == FORM and summary['metrics']['sharpe_ratio'] == 1.4
    # NaN and infinite metrics come back as null, as on the dashboard, never as invented numbers.
    assert summary['metrics']['serenity_index'] is None and summary['metrics']['omega_ratio'] is None
    assert summary['sections']['trades'] == {'count': 7}
    assert summary['sections']['equity_curve']['series'] == [{'name': 'Portfolio', 'points': 30}, {'name': 'BTC-USDT', 'points': 30}]
    assert summary['sections']['logs'] == {'log_size_bytes': 4}
    assert 'trades' not in summary and 'equity_curve' not in summary and 'strategy_codes' not in summary
    assert 'status_note' not in summary and summary['error'] is None
    assert 'machine running Jesse' not in summary  # location is added by the MCP layer only


def test_unfinished_and_failed_backtests_explain_their_state(api, stored):
    stored['backtest'][BACKTEST_ID] = _backtest_row(
        status='stopped', metrics=None, trades=None, equity_curve=None,
        exception='ValueError: bad route', traceback='x' * 10_000 + 'LAST LINE', description='d' * 9000)

    summary = _get(api, 'backtest', BACKTEST_ID)

    assert 'Stopped before finishing' in summary['status_note']
    assert summary['metrics'] is None and summary['sections']['trades'] == {'count': 0}
    assert summary['error']['exception'] == 'ValueError: bad route'
    assert summary['error']['traceback_tail'].endswith('LAST LINE') and summary['error']['traceback_truncated'] is True
    assert len(summary['error']['traceback_tail']) == session_results.MAX_TEXT_CHARS
    assert summary['description_truncated'] is True and len(summary['description']) == session_results.MAX_TEXT_CHARS

    stored['backtest'][BACKTEST_ID] = _backtest_row(status='running')
    assert 'Still running' in _get(api, 'backtest', BACKTEST_ID)['status_note']


def test_backtest_trades_are_paged_in_stored_order(api, stored):
    first = _get(api, 'backtest', BACKTEST_ID, 'trades', 0, 3)
    assert [t['id'] for t in first['items']] == ['trade-0', 'trade-1', 'trade-2']
    assert (first['total'], first['returned'], first['next_offset'], first['has_more']) == (7, 3, 3, True)

    last = _get(api, 'backtest', BACKTEST_ID, 'trades', 6, 3)
    assert [t['id'] for t in last['items']] == ['trade-6']
    assert (last['next_offset'], last['has_more']) == (None, False)
    assert _get(api, 'backtest', BACKTEST_ID, 'trades', 50, 3)['items'] == []


def test_pages_stop_at_the_byte_budget_and_refuse_oversized_items(api, stored, monkeypatch):
    monkeypatch.setattr(session_results, 'MAX_PAGE_BYTES', 700)
    page = _get(api, 'backtest', BACKTEST_ID, 'trades', 0, 50)
    assert 1 <= page['returned'] < 7 and page['truncated_by_size'] is True
    assert page['next_offset'] == page['returned'] and len(json.dumps(page['items'])) <= 700

    monkeypatch.setattr(session_results, 'MAX_PAGE_BYTES', 50)
    body = _refused(api, 'item_too_large', 413, section='trades')
    assert 'run_analysis' in body['message']


def test_equity_curves_are_paged_point_by_point_across_series(api, stored, monkeypatch):
    page = _get(api, 'backtest', BACKTEST_ID, 'equity_curve', 10, 5)
    assert [s['name'] for s in page['items']] == ['Portfolio', 'BTC-USDT']
    assert [p['value'] for p in page['items'][0]['points']] == [10_010, 10_011, 10_012, 10_013, 10_014]
    assert page['items'][0]['total_points'] == 30 and (page['total'], page['next_offset']) == (30, 15)

    monkeypatch.setattr(session_results, 'MAX_PAGE_BYTES', 900)
    shrunk = _get(api, 'backtest', BACKTEST_ID, 'equity_curve', 0, 30)
    assert shrunk['truncated_by_size'] is True and shrunk['returned'] < 30
    assert shrunk['next_offset'] == shrunk['returned'] and len(shrunk['items'][1]['points']) == shrunk['returned']


def test_logs_are_read_backwards_from_the_newest_line(api, stored, project, monkeypatch):
    log = project / 'storage' / 'logs' / 'backtest-mode' / f'{BACKTEST_ID}.txt'
    log.parent.mkdir(parents=True)
    log.write_text(''.join(f'line {i}\n' for i in range(10)) + 'x' * 5000 + '\n')

    newest = _get(api, 'backtest', BACKTEST_ID, 'logs', 0, 3)
    assert newest['items'][:2] == ['line 8', 'line 9'] and newest['items'][2].endswith('[line cut]')
    assert len(newest['items'][2]) == session_results.MAX_LOG_LINE_CHARS + len(' [line cut]')
    assert (newest['total'], newest['next_offset'], newest['available']) == (11, 3, True)
    older = _get(api, 'backtest', BACKTEST_ID, 'logs', 3, 5)
    assert older['items'] == [f'line {i}' for i in range(3, 8)]
    oldest = _get(api, 'backtest', BACKTEST_ID, 'logs', 8, 5)
    assert oldest['items'] == ['line 0', 'line 1', 'line 2'] and oldest['has_more'] is False

    # Only the end of a huge log is scanned.
    monkeypatch.setattr(session_results, 'MAX_LOG_SCAN_BYTES', 64)
    partial = _get(api, 'backtest', BACKTEST_ID, 'logs', 0, 2)
    assert partial['total'] is None and partial['has_more'] is True
    _refused(api, 'offset_too_large', 400, section='logs', offset=500)

    log.unlink()
    missing = _get(api, 'backtest', BACKTEST_ID, 'logs')
    assert missing['available'] is False and missing['items'] == []


def test_hyperparameters_section(api, stored):
    assert _get(api, 'backtest', BACKTEST_ID, 'hyperparameters')['items'] == [['fast', 10], ['slow', 30]]


# ---------------------------------------------------------------------------
# Optimization, Monte Carlo, significance tests
# ---------------------------------------------------------------------------

def test_optimization_summary_lists_leading_trials_and_pages_all_trials(api, stored):
    summary = _get(api, 'optimization', OPTIMIZATION_ID)
    assert (summary['completed_trials'], summary['total_trials'], summary['best_score']) == (40, 40, 0.9)
    assert len(summary['leading_trials']) == session_results.SUMMARY_TRIALS
    leader = summary['leading_trials'][0]
    assert leader['rank'] == '#1' and leader['params'] == {'fast': 0}
    assert set(leader['training_metrics']) == set(session_results.SUMMARY_TRIAL_METRICS)
    assert summary['sections']['best_trials'] == {'count': 5} and summary['sections']['objective_curve'] == {'count': 3}

    page = _get(api, 'optimization', OPTIMIZATION_ID, 'best_trials', 3, 10)
    assert [t['trial'] for t in page['items']] == ['Trial 103', 'Trial 104']
    assert page['items'][0]['testing_metrics']['calmar_ratio'] == 1.1  # every stored metric
    assert _get(api, 'optimization', OPTIMIZATION_ID, 'objective_curve')['items'] == [0.1, 0.2, 0.3]


def test_monte_carlo_summary_and_sections(api, stored):
    summary = _get(api, 'monte_carlo', MONTE_CARLO_ID)
    candles = summary['pipelines']['candles']
    assert list(summary['pipelines']) == ['candles']
    assert (candles['status'], candles['num_scenarios'], candles['pipeline_type']) == ('finished', 4, 'gaussian_noise')
    assert candles['summary_metrics'] == [{'metric': 'sharpe_ratio', 'original': 1.2, 'worst_5': 0.4, 'median': 1.0, 'best_5': 1.6}]

    analysis = _get(api, 'monte_carlo', MONTE_CARLO_ID, 'confidence_analysis')['items']
    assert analysis[0]['pipeline'] == 'candles' and analysis[0]['num_scenarios'] == 4

    metrics = _get(api, 'monte_carlo', MONTE_CARLO_ID, 'scenario_metrics')
    assert [m['scenario'] for m in metrics['items']] == ['original', 0, 1, 2, 3]
    assert metrics['items'][2]['metrics'] == {'sharpe_ratio': 1.02}
    assert 'equity_curve' not in metrics['items'][0] and 'trades' not in metrics['items'][0]

    curves = _get(api, 'monte_carlo', MONTE_CARLO_ID, 'equity_curves', 1, 2)
    assert [c['scenario'] for c in curves['items']] == [0, 1] and curves['items'][0]['name'] == 'Portfolio'
    assert curves['total'] == 5 and len(curves['items'][0]['data']) == 5

    logs = _get(api, 'monte_carlo', MONTE_CARLO_ID, 'logs')  # no log file: stored pipeline logs
    assert logs['source'] == 'database' and logs['items'] == ['[candles] first', '[candles] second']


def test_monte_carlo_without_results_yet(api, stored):
    row = _monte_carlo_row(with_results=False)
    row.status = 'running'
    stored['monte_carlo'][MONTE_CARLO_ID] = row
    assert _get(api, 'monte_carlo', MONTE_CARLO_ID, 'scenario_metrics')['items'] == []
    assert 'Still running' in _get(api, 'monte_carlo', MONTE_CARLO_ID)['status_note']


def test_significance_test_summary_holds_every_stored_result(api, stored):
    summary = _get(api, 'significance_test', SIGNIFICANCE_ID)
    assert summary['results'] == {'p_value': 0.03, 'observed_mean': 0.001, 'annualized_return': 0.2,
                                  'n_simulations': 2000, 'n_observations': 150}
    assert summary['has_chart'] is True and summary['form'] == FORM


# ---------------------------------------------------------------------------
# Live and paper sessions
# ---------------------------------------------------------------------------

def test_live_results_need_the_live_plugin(api, stored, monkeypatch):
    monkeypatch.setattr(session_results, '_live_plugin_available', lambda: False)
    monkeypatch.setattr(session_results, '_load_live', lambda _id: pytest.fail('read without plugin'))
    body = _refused(api, 'live_plugin_unavailable', 403, session_type='live', session_id=LIVE_ID)
    assert 'live trading plugin' in body['message']
    response = api.post('/session-results/live-sessions', json={}, headers=HEADERS)
    assert response.status_code == 403 and response.json()['error_type'] == 'live_plugin_unavailable'


def test_the_real_plugin_check_is_used_by_default(monkeypatch):
    monkeypatch.setenv('JESSE_DISABLE_LIVE_PLUGIN', 'TRUE')
    assert session_results._live_plugin_available() is False


def test_live_summary_counts_and_redacts_saved_credentials(api, live):
    summary = _get(api, 'live', LIVE_ID)

    text = json.dumps(summary)
    assert API_KEY not in text and API_SECRET not in text
    assert summary['error']['exception'] == 'AuthError: key [redacted] rejected'
    assert '[redacted]' in summary['error']['traceback_tail']
    assert (summary['session_mode'], summary['session_status'], summary['is_active']) == ('papertrade', 'stopped', False)
    assert summary['counts'] == {'trades': 12, 'orders': 5}
    assert summary['form']['exchange_api_key_id'] == 'key-id'  # the key's id is metadata, not a secret
    assert live.secrets_requested_with['exchange_api_key_id'] == 'key-id'
    assert 'Stopped before finishing' in summary['status_note']


def test_live_sections_page_database_rows(api, live):
    trades = _get(api, 'live', LIVE_ID, 'closed_trades', 10, 5)
    assert [t['id'] for t in trades['items']] == ['t10', 't11']
    assert (trades['total'], trades['next_offset'], trades['has_more']) == (12, None, False)
    first = _get(api, 'live', LIVE_ID, 'closed_trades', 0, 5)
    assert (first['next_offset'], first['has_more']) == (5, True)
    assert len(_get(api, 'live', LIVE_ID, 'orders')['items']) == 5
    assert _get(api, 'live', LIVE_ID, 'equity_curve', 0, 2)['items'][1] == {'time': 60_000, 'equity': 1001.0, 'currency': 'USDT'}

    logs = _get(api, 'live', LIVE_ID, 'logs', 0, 3)
    assert [entry['message'] for entry in logs['items']] == ['info 97', 'info 98', 'info 99']
    assert (logs['total'], logs['next_offset']) == (100, 3)
    errors = _get(api, 'live', LIVE_ID, 'error_logs')
    assert errors['items'] == [{'timestamp': 5, 'message': 'order failed: passphrase [redacted] invalid'}]


def test_live_session_list_is_compact(api, live):
    response = api.post('/session-results/live-sessions', json={'limit': 5}, headers=HEADERS)
    assert response.status_code == 200, response.text
    session = response.json()['sessions'][0]
    assert session['id'] == LIVE_ID and session['routes'] == FORM['routes'] and session['has_error'] is True
    assert 'state' not in session and 'strategy_codes' not in session and 'traceback' not in session
    assert api.post('/session-results/live-sessions', json={'limit': 101}, headers=HEADERS).status_code == 400


# ---------------------------------------------------------------------------
# Exports for analysis snapshots
# ---------------------------------------------------------------------------

def test_exports_hold_complete_arrays_and_live_exports_are_redacted(stored, live):
    backtest = session_results.export_session('backtest', BACKTEST_ID)
    assert len(backtest['trades']) == 7 and len(backtest['equity_curve'][0]['data']) == 30
    assert backtest['summary']['metrics']['sharpe_ratio'] == 1.4 and backtest['metrics']['serenity_index'] is None
    assert math.isclose(backtest['summary']['execution_duration'], 3.5)

    monte_carlo = session_results.export_session('monte_carlo', MONTE_CARLO_ID)
    assert len(monte_carlo['pipelines']['candles']['scenarios']) == 4 and monte_carlo['pipelines'].get('trades') is None
    assert len(session_results.export_session('optimization', OPTIMIZATION_ID)['best_trials']) == 5
    assert session_results.export_session('significance_test', SIGNIFICANCE_ID)['summary']['results']['p_value'] == 0.03

    exported = session_results.export_session('live', LIVE_ID)
    assert len(exported['closed_trades']) == 12 and len(exported['equity_curve']) == 9
    assert exported['complete'] is True and 'truncated' not in exported
    assert API_KEY not in json.dumps(exported) and API_SECRET not in json.dumps(exported)


def test_redaction_ignores_short_values_and_replaces_longest_first():
    secrets = session_results._redact('k=abcdefgh-long, short=abc', ['abcdefgh-long', 'abcdefgh'])
    assert secrets == 'k=[redacted], short=abc'
    assert session_results._redact({'a': ['x abcdefgh y', 1]}, ['abcdefgh']) == {'a': ['x [redacted] y', 1]}


def test_live_secret_lookup_covers_nested_fields_and_malformed_json(monkeypatch):
    from jesse.models.ExchangeApiKeys import ExchangeApiKeys
    from jesse.models.NotificationApiKeys import NotificationApiKeys
    key_id = '66666666-6666-4666-8666-666666666666'
    exchange = SimpleNamespace(api_key=API_KEY, api_secret=API_SECRET, additional_fields='{not json')
    notification = SimpleNamespace(fields=json.dumps({'bot_token': 'bot-token-123456', 'targets': [{'chat_id': 987654321}]}))
    monkeypatch.setattr(ExchangeApiKeys, 'get_or_none', lambda *args: exchange)
    monkeypatch.setattr(NotificationApiKeys, 'get_or_none', lambda *args: notification)
    form = {'exchange_api_key_id': key_id, 'notification_api_key_id': key_id}

    # A malformed extra-fields column must not switch off redaction of the key and secret.
    assert {API_KEY, API_SECRET, 'bot-token-123456', '987654321'} <= set(session_results._live_secrets(form))
    exchange.additional_fields = json.dumps({'passphrase': PASSPHRASE, 'nested': {'private_key': 'pk-0123456789'}})
    assert {PASSPHRASE, 'pk-0123456789'} <= set(session_results._live_secrets(form))

    # Values that cannot reference a saved key (a draft's empty or placeholder ID) are not looked up.
    monkeypatch.setattr(ExchangeApiKeys, 'get_or_none', lambda *args: pytest.fail('looked up'))
    monkeypatch.setattr(NotificationApiKeys, 'get_or_none', lambda *args: pytest.fail('looked up'))
    assert session_results._live_secrets({'exchange_api_key_id': '', 'notification_api_key_id': 'key-id'}) == []


def test_live_reads_fail_closed_when_saved_keys_cannot_be_read(api, live, monkeypatch):
    def unreadable(_form):
        raise RuntimeError('relation "exchangeapikeys" does not exist')

    monkeypatch.setattr(session_results, '_live_secrets', unreadable)
    body = _refused(api, 'read_failed', 500, session_type='live', session_id=LIVE_ID)
    assert API_KEY not in json.dumps(body) and API_SECRET not in json.dumps(body)
    with pytest.raises(RuntimeError):
        session_results.export_session('live', LIVE_ID)


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------

@pytest.fixture
def tools(api, monkeypatch):
    def forward_post(url, json=None, headers=None, timeout=None):
        return api.post(url.removeprefix('http://jesse.test'), json=json, headers=headers)

    monkeypatch.setattr(project_files_service.mcp_config, 'JESSE_API_URL', 'http://jesse.test')
    monkeypatch.setattr(project_files_service.mcp_config, 'JESSE_PASSWORD', PASSWORD)
    monkeypatch.setattr(project_files_service.requests, 'post', forward_post)
    mcp = FakeMCP()
    register_tools(mcp)
    return mcp.tools


def test_mcp_tools_read_results_through_the_api(tools, stored, live):
    summary = tools['get_session_results']('backtest', BACKTEST_ID)
    assert summary['status'] == 'success' and summary['action'] == 'get_session_results'
    assert 'machine running Jesse' in summary['location']
    page = tools['get_session_results']('live', LIVE_ID, 'closed_trades', 0, 2)
    assert [t['id'] for t in page['items']] == ['t0', 't1']
    listed = tools['get_live_sessions']()
    assert listed['sessions'][0]['id'] == LIVE_ID

    refused = tools['get_session_results']('backtest', BACKTEST_ID, 'nonsense')
    assert (refused['status'], refused['error_type']) == ('error', 'invalid_request')
