"""Research runners on the MCP side: `where` on the run tools, the queued response, and list_runners."""
import asyncio
import copy
import importlib
import json
from types import SimpleNamespace

import pytest

import jesse.mcp.mcp_config as mcp_config
from jesse.mcp.tools.backtest import register_backtest_tools
from jesse.mcp.tools.services import backtest as backtest_service
from jesse.mcp.tools.services import monte_carlo as monte_carlo_service
from jesse.mcp.tools.services import optimization as optimization_service
from jesse.mcp.tools.services import session_wait
from jesse.mcp.tools.services import session_config
from jesse.mcp.tools.services import significance_test as significance_test_service
from jesse.mcp.tools.session_results import register_session_results_tools

# Imported by its full name: a star import in the services package shadows the attribute name.
project_files = importlib.import_module('jesse.mcp.tools.services.project_files')

SID = 'draft-id'
FUTURES = 'Binance Perpetual Futures'
ROUTES = json.dumps([{'exchange': FUTURES, 'strategy': 'ExampleStrategy', 'symbol': 'BTC-USDT', 'timeframe': '4h'}])

# name: (service module, draft creator, run service, session type, API prefix, start route, start answers 202)
RUNS = {
    'backtest': (backtest_service, 'create_backtest_draft_service', 'run_backtest_service',
                 'backtest', 'backtest', '/backtest', True),
    'optimization': (optimization_service, 'create_optimization_draft_service', 'run_optimization_service',
                     'optimization', 'optimization', '/optimization/resume', False),
    'optimization_rerun': (optimization_service, 'create_optimization_draft_service', 'rerun_optimization_service',
                           'optimization', 'optimization', '/optimization/rerun', True),
    'monte_carlo': (monte_carlo_service, 'create_monte_carlo_draft_service', 'run_monte_carlo_service',
                    'monte_carlo', 'monte-carlo', '/monte-carlo/resume', False),
    'monte_carlo_resume': (monte_carlo_service, 'create_monte_carlo_draft_service', 'resume_monte_carlo_service',
                           'monte_carlo', 'monte-carlo', '/monte-carlo/resume', False),
    'significance_test': (significance_test_service, 'create_significance_test_draft_service',
                          'run_significance_test_service', 'significance_test', 'significance-test',
                          '/significance-test', True),
}


def _reply(status_code: int, body=None):
    if body is None:
        # Like a reply whose body the caller never parses: no JSON at all.
        return SimpleNamespace(status_code=status_code, text='')
    return SimpleNamespace(status_code=status_code, text=json.dumps(body), json=lambda: copy.deepcopy(body))


class FakeJesse:
    """Stores the draft a create tool writes, serves it back, and answers the start route."""

    def __init__(self, prefix: str, start_route: str):
        self.prefix = prefix
        self.start_route = start_route
        self.state = None
        self.status = 'draft'
        self.posts = []
        self.start_reply = _reply(202, {'message': 'Started...'})

    def __call__(self, url, json=None, headers=None, timeout=None, **kwargs):
        self.posts.append((url, json))
        if url.endswith('/update-state'):
            self.state = copy.deepcopy(json['state'])
            return _reply(200, {'message': 'ok'})
        if url.endswith('/notes'):
            return _reply(200, {'message': 'ok'})
        if url.endswith(f'/{self.prefix}/sessions/{SID}'):
            return _reply(200, {'session': {'id': SID, 'status': self.status, 'state': copy.deepcopy(self.state)}})
        if url.endswith(self.start_route):
            return self.start_reply
        raise AssertionError(f'unexpected request to {url}')

    def starts(self) -> list:
        return [payload for url, payload in self.posts if url.endswith(self.start_route)]


@pytest.fixture(autouse=True)
def no_saved_settings(monkeypatch):
    monkeypatch.setattr(session_config, 'load_saved_settings', lambda: {})
    monkeypatch.setattr(mcp_config, 'DASHBOARD_URL', 'http://dashboard.test')


def _drafted(monkeypatch, name: str):
    service, creator, runner, session_type, prefix, start_route, _ = RUNS[name]
    jesse = FakeJesse(prefix, start_route)
    monkeypatch.setattr(service.requests, 'post', jesse)
    monkeypatch.setattr(service, 'hash_password', lambda password: 'hashed')
    monkeypatch.setattr(service.uuid, 'uuid4', lambda: SID)
    created = getattr(service, creator)(exchange=FUTURES, routes=ROUTES)
    assert created['status'] == 'success', created
    if name == 'optimization_rerun':
        jesse.status = 'finished'
    jesse.posts.clear()
    return jesse, getattr(service, runner), session_type


def _queued_body(name: str, target: str = 'macmini', warning: bool = True) -> tuple:
    body = {
        'status': 'queued', 'session_id': SID, 'job_id': 'job-1', 'target': target,
        'message': f'Queued for {"any runner" if target == "any" else "runner " + target}.',
    }
    if warning:
        body['warning'] = 'No runner that can take it is connected right now; it starts when one is.'
    if RUNS[name][6]:
        return 202, body
    # The resume routes answer 200 with the session next to the queue fields.
    return 200, {'session': {'id': SID, 'status': 'queued'}, **body}


# ---------------------------------------------------------------------------
# `where` reaches Jesse
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('name', sorted(RUNS))
def test_where_defaults_to_auto_and_is_sent_with_the_start(monkeypatch, name):
    jesse, run, _ = _drafted(monkeypatch, name)

    run(SID)
    run(SID, where='  macmini ')

    assert [payload['where'] for payload in jesse.starts()] == ['auto', 'macmini']


@pytest.mark.parametrize('name', sorted(RUNS))
@pytest.mark.parametrize('where', ['', '   ', None, 5, ['local']])
def test_an_invalid_where_is_refused_before_calling_jesse(monkeypatch, name, where):
    jesse, run, _ = _drafted(monkeypatch, name)

    result = run(SID, where=where)

    assert result['status'] == 'error' and result['error_type'] == 'invalid_request'
    assert 'list_runners' in result['message']
    assert jesse.posts == []


def test_the_run_tool_refuses_an_invalid_where_before_metering(monkeypatch):
    tools = {}

    class Registrar:
        def tool(self, *args, **kwargs):
            def decorator(func):
                tools[func.__name__] = func
                return func
            return decorator

    register_backtest_tools(Registrar())
    called = []
    monkeypatch.setattr('jesse.mcp.tools.backtest.run_blocking', lambda *args, **kwargs: called.append(args))

    result = asyncio.run(tools['run_backtest'](SID, where=' '))

    assert result['status'] == 'error' and called == []


# ---------------------------------------------------------------------------
# Queued and started responses
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('name', sorted(RUNS))
def test_a_queued_start_returns_status_queued(monkeypatch, name):
    jesse, run, session_type = _drafted(monkeypatch, name)
    jesse.start_reply = _reply(*_queued_body(name))

    result = run(SID, where='macmini')

    assert result['status'] == 'queued'
    assert (result['session_id'], result['target'], result['job_id']) == (SID, 'macmini', 'job-1')
    assert result['dashboard_url'] == mcp_config.dashboard_url(session_type, SID) != ''
    assert result['warning'].startswith('No runner that can take it')
    assert result['message'] == 'Queued for runner macmini. Call wait_for_sessions([session_id]) to wait for it.'
    if name == 'backtest':
        assert result['backtest_id'] == SID and result['routes'][0]['strategy'] == 'ExampleStrategy'


@pytest.mark.parametrize('name', sorted(RUNS))
def test_a_run_queued_for_any_runner_without_warning(monkeypatch, name):
    jesse, run, _ = _drafted(monkeypatch, name)
    jesse.start_reply = _reply(*_queued_body(name, target='any', warning=False))

    result = run(SID, where='any')

    assert result['status'] == 'queued' and result['target'] == 'any'
    assert 'warning' not in result
    assert result['message'] == 'Queued for any runner. Call wait_for_sessions([session_id]) to wait for it.'


@pytest.mark.parametrize('name', sorted(RUNS))
@pytest.mark.parametrize('body', [{'message': 'Started...'}, None])
def test_a_local_start_still_reports_started(monkeypatch, name, body):
    jesse, run, session_type = _drafted(monkeypatch, name)
    if RUNS[name][6]:
        jesse.start_reply = _reply(202, body)
    else:
        jesse.start_reply = _reply(200, {'session': {'id': SID, 'status': 'running'}} if body else None)

    result = run(SID)

    assert result['status'] == 'started'
    assert result['dashboard_url'] == mcp_config.dashboard_url(session_type, SID)
    assert 'started' in result['message'] and 'wait_for_sessions' in result['message']
    assert not {'target', 'job_id', 'warning'} & set(result)


@pytest.mark.parametrize('name', sorted(RUNS))
def test_a_refused_where_shows_jesses_reason(monkeypatch, name):
    jesse, run, _ = _drafted(monkeypatch, name)
    jesse.start_reply = _reply(400, {'error': 'No runner is named "nope". Known runners: macmini.'})

    result = run(SID, where='nope')

    assert result['status'] == 'error'
    assert 'No runner is named "nope"' in result['message']


@pytest.mark.parametrize('name', ['optimization', 'monte_carlo', 'significance_test'])
def test_a_conflict_keeps_its_message_and_adds_jesses_reason(monkeypatch, name):
    jesse, run, _ = _drafted(monkeypatch, name)
    jesse.start_reply = _reply(409, {'error': 'This session is already running on a runner.'})

    result = run(SID)

    assert result['status'] == 'error'
    assert 'already' in result['message']
    assert result['details'] == 'This session is already running on a runner.'


@pytest.mark.parametrize('name', ['optimization', 'optimization_rerun', 'monte_carlo', 'monte_carlo_resume'])
def test_a_session_already_queued_is_not_queued_again(monkeypatch, name):
    jesse, run, session_type = _drafted(monkeypatch, name)
    jesse.status = 'queued'

    result = run(SID)

    assert result['status'] == 'queued'
    assert result['dashboard_url'] == mcp_config.dashboard_url(session_type, SID)
    assert 'already queued' in result['message']
    assert jesse.starts() == []


# ---------------------------------------------------------------------------
# list_runners
# ---------------------------------------------------------------------------

RUNNERS = {
    'status': 'success', 'enabled': True, 'hub_jesse_version': '3.2.1', 'queued_jobs': 2,
    'runners': [{
        'name': 'macmini', 'role': 'runner', 'host': '192.168.1.103', 'alive': True, 'last_seen_seconds_ago': 4.2,
        'cores_budget': 9, 'cores_used': 4, 'cores_free': 5, 'cpu_cores': 10, 'jesse_version': '3.2.1', 'compatible': True,
        'running': [{'session_id': 'abc', 'session_type': 'optimization'}],
    }],
}


@pytest.fixture
def api(monkeypatch):
    calls = []
    replies = []

    def post(url, json=None, headers=None, timeout=None):
        calls.append((url, json, headers))
        return replies.pop(0)

    monkeypatch.setattr(mcp_config, 'JESSE_API_URL', 'http://jesse.test')
    monkeypatch.setattr(mcp_config, 'JESSE_PASSWORD', 'secret')
    monkeypatch.setattr(project_files.requests, 'post', post)
    return SimpleNamespace(calls=calls, replies=replies)


def test_list_runners_reads_the_runners_route(api):
    api.replies.append(_reply(200, RUNNERS))

    result = session_wait.list_runners_service()

    assert api.calls[0][0] == 'http://jesse.test/session-results/runners'
    assert api.calls[0][1] == {}
    assert result['status'] == 'success' and result['action'] == 'list_runners'
    assert (result['enabled'], result['hub_jesse_version'], result['queued_jobs']) == (True, '3.2.1', 2)
    assert result['runners'] == RUNNERS['runners']


def test_list_runners_on_a_jesse_without_runners(api):
    api.replies.append(_reply(404, {'detail': 'Not Found'}))

    result = session_wait.list_runners_service()

    assert result['status'] == 'error' and result['http_status'] == 404
    assert 'no research runners' in result['message']


def test_list_runners_passes_on_jesses_read_error(api):
    api.replies.append(_reply(500, {'status': 'error', 'error_type': 'read_failed', 'message': 'Jesse could not read the runners (OperationalError).'}))

    result = session_wait.list_runners_service()

    assert (result['status'], result['error_type']) == ('error', 'read_failed')


def test_list_runners_is_a_registered_read_only_tool(monkeypatch):
    tools = {}

    class Registrar:
        def tool(self, *args, **kwargs):
            def decorator(func):
                tools[func.__name__] = func
                return func
            return decorator

    register_session_results_tools(Registrar())
    seen = []

    async def run_blocking(func, *args, **kwargs):
        seen.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr('jesse.mcp.tools.session_results.run_blocking', run_blocking)
    monkeypatch.setattr('jesse.mcp.tools.services.session_wait._call', lambda *args: {'status': 'success', 'runners': []})

    assert asyncio.run(tools['list_runners']()) == {'status': 'success', 'runners': []}
    assert seen[0].__name__ == 'list_runners_service'
    assert 'machines that share its database' in tools['list_runners'].__doc__
