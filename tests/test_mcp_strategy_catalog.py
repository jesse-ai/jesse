import json
import re
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

import jesse.mcp.tools.services.strategy_catalog as catalog_service
from jesse.controllers import auth_controller, strategy_controller
from jesse.mcp.agent_rules import _load_packaged_rules
from jesse.mcp.resources import register_resources
from jesse.mcp.tools import register_tools
from jesse.services import auth
from tests.mcp_tool_adapters import callable_tool


PASSWORD = 'strategy-catalog-password'
JESSE_URL = 'http://jesse.test'
API2_URL = 'http://api2.test'
DASHBOARD = 'http://localhost:9000'
FREE_LICENSE = 'license-free-account'
PREMIUM_LICENSE = 'license-premium-account'
PERIODS = ['2024 - 2025', 'Q1 of 2025', 'Q2 of 2025', 'Q3 of 2025', 'Q4 of 2025', 'Q1 of 2026', 'Q2 of 2026']
DEFAULT_PERIOD = 'Q1 of 2026'  # the dashboard's default: the second most recent period
SORT_FIELDS = {
    'Sharpe Ratio': 'sharpe_ratio',
    'PNL': 'net_profit_percentage',
    'Sortino Ratio': 'sortino_ratio',
    'Calmar Ratio': 'calmar_ratio',
    'Win Rate': 'win_rate',
}


def _code(class_name: str) -> str:
    return f'from jesse.strategies import Strategy\n\n\nclass {class_name}(Strategy):\n    pass\n'


def _metrics(sharpe, pnl, sortino, calmar, win_rate, status='completed', symbol='BTC-USDT', timeframe='4h'):
    return {
        'id': 'metric-id', 'strategy_id': 'strategy-id', 'status': status,
        'exchange': 'Binance Perpetual Futures', 'symbol': symbol, 'timeframe': timeframe,
        'starting_date': '2026-01-01T00:00:00Z', 'finishing_date': '2026-03-31T00:00:00Z',
        'sharpe_ratio': sharpe, 'net_profit_percentage': pnl, 'sortino_ratio': sortino,
        'calmar_ratio': calmar, 'win_rate': win_rate, 'max_drawdown': -12.5, 'annual_return': 30.1,
        'total_completed_trades': 40, 'expectancy': 1.2,
        'equity_curve': [{'time': i, 'value': 1000 + i} for i in range(500)],
        'created_at': '2026-04-01T00:00:00Z', 'updated_at': '2026-04-01T00:00:00Z',
    }


def _strategy(slug, name, class_name, type_, author, description, submitted, metrics, admin_status='approved'):
    return {
        'id': slug, 'slug': slug, 'name': name, 'type': type_, 'description': description,
        'user': {'username': author}, 'created_at': submitted, 'views': 10,
        'symbol': 'BTC-USDT', 'timeframe': '4h',
        'backtest_symbols': ['BTC-USDT', 'ETH-USDT'], 'backtest_timeframes': ['1h', '4h'],
        'admin_status': admin_status, 'code': _code(class_name), 'strategy_metrics': metrics,
    }


def _catalog():
    return [
        _strategy('trend-rider', 'Trend Rider', 'TrendRider', 'free', 'alice', 'EMA crossover with ATR stops',
                  '2026-02-10T08:00:00Z', _metrics(1.5, 20.0, 2.0, 1.0, 0.40)),
        _strategy('mean-revert-pro', 'Mean Revert Pro', 'MeanRevertPro', 'premium', 'bob', 'Bollinger mean reversion',
                  '2026-03-05T08:00:00Z', _metrics(2.5, 10.0, 1.0, 3.0, 0.60)),
        _strategy('breakout-hunter', 'Breakout Hunter', 'BreakoutHunter', 'free', 'Carol', 'Donchian breakouts on trend days',
                  '2025-11-20T08:00:00Z', _metrics(0.5, 35.0, 3.0, 2.0, 0.55)),
        _strategy('pending-idea', 'Pending Idea', 'PendingIdea', 'free', 'dave', 'Not reviewed yet',
                  '2026-03-10T08:00:00Z', _metrics(9.9, 99.0, 9.9, 9.9, 0.99), admin_status='pending'),
        _strategy('still-running', 'Still Running', 'StillRunning', 'free', 'erin', 'Metrics not finished',
                  '2026-03-11T08:00:00Z', _metrics(9.9, 99.0, 9.9, 9.9, 0.99, status='running')),
        _strategy('no-class-here', 'No Class', '', 'free', 'frank', 'Broken upload',
                  '2025-06-01T08:00:00Z', _metrics(0.1, 1.0, 0.1, 0.1, 0.10)),
    ]


def _json_response(status: int, body) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = json.dumps(body).encode('utf-8')
    response.headers['Content-Type'] = 'application/json'
    return response


class FakeJesseTrade:
    """
    The api2 (jesse.trade) routes Jesse proxies, reproducing the Go handlers' contract:

    - /auth/exchange-token turns a known LICENSE_API_TOKEN into a session token and answers
      401 {"message": "invalid license API token"} otherwise.
    - /strategies requires a period from /strategies/periods (400 otherwise), filters
      created_at >= submitted_after and <= submitted_before (dates at 00:00 UTC), keeps only
      approved strategies with completed metrics, ranks best first, and ranks any unknown
      sort_by label as Sharpe Ratio.
    - Strategy code is only sent to a signed-in account: every free strategy, premium ones
      only to Premium accounts (and their author, which these tests do not need). Guests get
      an empty string.
    - Unknown routes and slugs answer 404 {"message": ...}, the shape of api2's JSONError.
    - /strategies/{slug}/metrics answers 404 for an unknown slug or an untested combination.
    """

    def __init__(self):
        self.strategies = _catalog()
        self.sessions = {'session-free': 'free', 'session-premium': 'premium'}
        self.licenses = {FREE_LICENSE: 'session-free', PREMIUM_LICENSE: 'session-premium'}
        self.requests = []
        self.down = False

    def _plan(self, headers):
        bearer = (headers or {}).get('Authorization', '')
        return self.sessions.get(bearer.removeprefix('Bearer '))

    def _public(self, strategy, plan):
        visible = dict(strategy)
        can_see_code = plan is not None and (strategy['type'] == 'free' or plan == 'premium')
        visible['code'] = strategy['code'] if can_see_code else ''
        return visible

    def handle(self, method, path, params, json_body, headers):
        self.requests.append({'method': method, 'path': path, 'params': dict(params or {}), 'headers': dict(headers or {})})
        if self.down:
            raise requests.exceptions.ConnectionError('api2.test is unreachable')

        if method == 'POST' and path == '/auth/exchange-token':
            session = self.licenses.get((json_body or {}).get('license_api_token'))
            if session is None:
                return _json_response(401, {'message': 'invalid license API token'})
            return _json_response(200, {'access_token': session, 'user': {'email': 'private@example.com'}})

        if method == 'GET' and path == '/strategies/periods':
            return _json_response(200, {'periods': PERIODS})

        plan = self._plan(headers)
        if method == 'GET' and path == '/strategies':
            params = params or {}
            if params.get('period') not in PERIODS:
                return _json_response(400, {'message': 'invalid period format'})
            field = SORT_FIELDS.get(params.get('sort_by', ''), 'sharpe_ratio')
            after, before = params.get('submitted_after'), params.get('submitted_before')
            listed = [
                s for s in self.strategies
                if s['admin_status'] == 'approved' and s['strategy_metrics']['status'] == 'completed'
                and (not after or s['created_at'] >= f'{after}T00:00:00Z')
                and (not before or s['created_at'] <= f'{before}T00:00:00Z')
            ]
            listed.sort(key=lambda s: s['strategy_metrics'][field], reverse=True)
            return _json_response(200, {'strategies': [self._public(s, plan) for s in listed]})

        match = re.fullmatch(r'/strategies/([^/]+)(/metrics)?', path)
        strategy = next((s for s in self.strategies if match and s['slug'] == match.group(1)), None)
        if method == 'GET' and match and not match.group(2):
            if strategy is None:
                return _json_response(404, {'message': 'strategy not found'})
            return _json_response(200, self._public(strategy, plan))
        if method == 'GET' and match:
            if strategy is None:
                return _json_response(404, {'message': 'strategy not found'})
            if params.get('symbol') == 'SOL-USDT' or params.get('period') not in PERIODS:
                return _json_response(404, {'message': 'strategy metrics not found'})
            return _json_response(200, _metrics(1.1, 5.0, 1.2, 0.9, 0.5, symbol=params['symbol'], timeframe=params['timeframe']))

        return _json_response(404, {'message': 'not found'})


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


@pytest.fixture
def project(tmp_path, monkeypatch) -> Path:
    """A disposable Jesse project; the strategy handler resolves strategies/ from the working directory."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'strategies').mkdir()
    return tmp_path


@pytest.fixture
def jesse_trade() -> FakeJesseTrade:
    return FakeJesseTrade()


@pytest.fixture
def network(project, jesse_trade, monkeypatch):
    """
    Serves the MCP worker's calls with Jesse's real strategy and auth routers in-process, and
    Jesse's outgoing jesse.trade calls with FakeJesseTrade. Returns the list of Jesse calls.
    """
    monkeypatch.setitem(auth.ENV_VALUES, 'PASSWORD', PASSWORD)
    monkeypatch.setitem(auth_controller.ENV_VALUES, 'LICENSE_API_TOKEN', FREE_LICENSE)
    monkeypatch.setattr(strategy_controller, 'JESSE_API2_URL', API2_URL)
    monkeypatch.setattr(auth_controller, 'JESSE_API2_URL', API2_URL)
    monkeypatch.setattr(catalog_service.mcp_config, 'JESSE_API_URL', JESSE_URL)
    monkeypatch.setattr(catalog_service.mcp_config, 'JESSE_PASSWORD', PASSWORD)
    monkeypatch.setattr(catalog_service.mcp_config, 'DASHBOARD_URL', DASHBOARD)

    app = FastAPI()

    @app.exception_handler(auth.InvalidAuthError)
    async def invalid_auth_handler(_request, _exc):
        return auth.unauthorized_response()

    app.include_router(strategy_controller.router)
    app.include_router(auth_controller.router)
    client = TestClient(app)
    jesse_calls = []

    def route(method, url, params=None, json=None, headers=None, timeout=None, **_kwargs):
        assert timeout, 'every outgoing request must have a timeout'
        parts = urlsplit(url)
        if url.startswith(JESSE_URL):
            jesse_calls.append({'method': method, 'path': parts.path, 'params': dict(params or {}), 'headers': dict(headers or {})})
            return client.request(method, parts.path, params=params, json=json, headers=headers)
        if url.startswith(API2_URL):
            return jesse_trade.handle(method, parts.path, params, json, headers)
        raise AssertionError(f'unexpected outgoing request to {url}')

    # The MCP service calls requests.request; Jesse's controllers call requests.get/post.
    monkeypatch.setattr(requests, 'request', route)
    monkeypatch.setattr(requests, 'get', lambda url, **kwargs: route('GET', url, **kwargs))
    monkeypatch.setattr(requests, 'post', lambda url, **kwargs: route('POST', url, **kwargs))
    return jesse_calls


@pytest.fixture
def tools(network):
    mcp = FakeMCP()
    register_tools(mcp)
    return mcp.tools


def _assert_no_secrets(result: dict) -> None:
    dumped = json.dumps(result)
    for secret in (FREE_LICENSE, PREMIUM_LICENSE, 'session-free', 'session-premium', PASSWORD,
                   sha256(PASSWORD.encode('utf-8')).hexdigest(), 'private@example.com'):
        assert secret not in dumped


def _slugs(result: dict) -> list:
    return [strategy['slug'] for strategy in result['strategies']]


def test_catalog_tools_are_registered_apart_from_local_strategy_tools():
    mcp = FakeMCP()
    register_tools(mcp)

    catalog_tools = {'browse_strategy_catalog', 'get_catalog_strategy_metrics', 'import_catalog_strategy'}
    assert catalog_tools <= set(mcp.tools)
    assert {'create_strategy', 'read_strategy', 'write_strategy'} <= set(mcp.tools)

    browse_docs = mcp.tools['browse_strategy_catalog'].__doc__
    import_docs = mcp.tools['import_catalog_strategy'].__doc__
    assert browse_docs is not None and import_docs is not None
    assert 'NOT the strategies installed in this Jesse project' in browse_docs
    assert 'import_catalog_strategy(slug)' in browse_docs
    assert 'Never present an error as an' in browse_docs
    assert 'continue with the returned local_name' in import_docs
    assert 'Only import a strategy the user' in import_docs


def test_browse_uses_the_dashboard_default_period_and_ranking(tools, network, jesse_trade):
    result = tools['browse_strategy_catalog']()

    assert result['status'] == 'success'
    assert result['filters']['period'] == DEFAULT_PERIOD
    assert result['filters']['sort_by'] == 'Sharpe Ratio'
    assert result['available_filters'] == {
        'periods': PERIODS,
        'default_period': DEFAULT_PERIOD,
        'sort_by': ['Sharpe Ratio', 'PNL', 'Sortino Ratio', 'Calmar Ratio', 'Win Rate'],
        'strategy_type': ['free', 'premium'],
    }
    # Unapproved strategies and unfinished metrics are hidden by jesse.trade, as on the dashboard.
    assert _slugs(result) == ['mean-revert-pro', 'trend-rider', 'breakout-hunter', 'no-class-here']
    assert result['jesse_trade_signed_in'] is True
    assert result['jesse_trade_auth'] is None

    trend = result['strategies'][1]
    assert trend['name'] == 'Trend Rider'
    assert trend['author'] == 'alice'
    assert trend['type'] == 'free'
    assert trend['code_available'] is True
    assert trend['backtest_symbols'] == ['BTC-USDT', 'ETH-USDT']
    assert trend['metrics']['sharpe_ratio'] == 1.5
    assert set(trend['metrics']) == set(catalog_service._SUMMARY_METRICS)
    # A free account cannot import premium code, and jesse.trade signals that by withholding it.
    assert result['strategies'][0]['code_available'] is False
    # Code and equity curves are never copied into the tool result.
    assert 'code' not in trend
    assert 'equity_curve' not in json.dumps(result)

    index_call = next(call for call in network if call['path'] == '/strategy/index')
    assert index_call['params'] == {'period': DEFAULT_PERIOD, 'sort_by': 'Sharpe Ratio'}
    assert index_call['headers']['X-Jesse-Trade-Token'] == 'session-free'
    api2_index = next(r for r in jesse_trade.requests if r['path'] == '/strategies')
    assert api2_index['headers']['Authorization'] == 'Bearer session-free'
    _assert_no_secrets(result)


@pytest.mark.parametrize(('sort_by', 'expected'), [
    ('PNL', ['breakout-hunter', 'trend-rider', 'mean-revert-pro', 'no-class-here']),
    ('Sortino Ratio', ['breakout-hunter', 'trend-rider', 'mean-revert-pro', 'no-class-here']),
    ('Calmar Ratio', ['mean-revert-pro', 'breakout-hunter', 'trend-rider', 'no-class-here']),
    ('Win Rate', ['mean-revert-pro', 'breakout-hunter', 'trend-rider', 'no-class-here']),
])
def test_browse_sends_the_dashboard_sort_labels(tools, jesse_trade, sort_by, expected):
    result = tools['browse_strategy_catalog'](period='Q4 of 2025', sort_by=sort_by)

    assert result['status'] == 'success'
    assert _slugs(result) == expected
    api2_index = next(r for r in jesse_trade.requests if r['path'] == '/strategies')
    assert api2_index['params'] == {'period': 'Q4 of 2025', 'sort_by': sort_by}


def test_browse_forwards_submission_dates_to_jesse_trade(tools, jesse_trade):
    result = tools['browse_strategy_catalog'](submitted_after='2026-01-01', submitted_before='2026-03-01')

    assert result['status'] == 'success'
    assert _slugs(result) == ['trend-rider']
    assert result['filters']['submitted_after'] == '2026-01-01'
    assert result['filters']['submitted_before'] == '2026-03-01'
    api2_index = next(r for r in jesse_trade.requests if r['path'] == '/strategies')
    assert api2_index['params']['submitted_after'] == '2026-01-01'
    assert api2_index['params']['submitted_before'] == '2026-03-01'


@pytest.mark.parametrize(('kwargs', 'fragment'), [
    ({'sort_by': 'Profit Factor'}, 'sort_by must be one of'),
    ({'sort_by': 'sharpe_ratio'}, 'sort_by must be one of'),
    ({'strategy_type': 'paid'}, 'strategy_type must be one of'),
    ({'submitted_after': '2026/01/01'}, 'submitted_after must be a date'),
    ({'submitted_before': '2026-02-30'}, 'submitted_before must be a date'),
    ({'submitted_after': '2026-03-02', 'submitted_before': '2026-03-01'}, 'must not be later'),
    ({'offset': -1}, 'offset must be 0 or greater'),
    ({'limit': 0}, 'limit must be between 1 and 25'),
    ({'limit': 26}, 'limit must be between 1 and 25'),
])
def test_browse_rejects_unsupported_arguments_before_any_request(tools, network, kwargs, fragment):
    result = tools['browse_strategy_catalog'](**kwargs)

    assert result['status'] == 'error'
    assert result['error_type'] == 'invalid_request'
    assert fragment in result['message']
    # jesse.trade would silently rank an unknown sort label by Sharpe Ratio instead.
    assert network == []


def test_browse_rejects_a_period_the_catalog_does_not_have(tools, jesse_trade):
    result = tools['browse_strategy_catalog'](period='Q1 of 2019')

    assert result['status'] == 'error'
    assert result['error_type'] == 'invalid_period'
    assert result['available_periods'] == PERIODS
    assert not any(r['path'] == '/strategies' for r in jesse_trade.requests)


def test_browse_search_type_filter_and_pagination_keep_the_ranking(tools):
    first = tools['browse_strategy_catalog'](strategy_type='FREE', limit=2)
    assert first['filters']['strategy_type'] == 'free'
    assert _slugs(first) == ['trend-rider', 'breakout-hunter']
    assert first['pagination'] == {
        'offset': 0, 'limit': 2, 'returned': 2, 'total_matches': 3,
        'total_ranked_in_period': 4, 'has_more': True, 'next_offset': 2,
    }

    second = tools['browse_strategy_catalog'](strategy_type='free', limit=2, offset=first['pagination']['next_offset'])
    assert _slugs(second) == ['no-class-here']
    assert second['pagination']['has_more'] is False
    assert second['pagination']['next_offset'] is None
    assert second['message'] == 'Showing 3-3 of 3 matching catalog strategies for Q1 of 2026.'

    # Matches name, description, author, and slug case-insensitively.
    assert _slugs(tools['browse_strategy_catalog'](query='  carol ')) == ['breakout-hunter']
    assert _slugs(tools['browse_strategy_catalog'](query='MEAN REVERSION')) == ['mean-revert-pro']
    assert _slugs(tools['browse_strategy_catalog'](query='trend')) == ['trend-rider', 'breakout-hunter']
    # Each field is matched on its own, so text spanning the name and description does not match.
    assert _slugs(tools['browse_strategy_catalog'](query='Rider EMA')) == []

    past_end = tools['browse_strategy_catalog'](offset=10)
    assert past_end['status'] == 'success'
    assert past_end['strategies'] == []
    assert past_end['message'] == 'offset 10 is past the last of 4 matching strategies.'


def test_browse_explains_empty_results(tools, jesse_trade):
    no_match = tools['browse_strategy_catalog'](query='grid martingale')
    assert no_match['status'] == 'success'
    assert no_match['strategies'] == []
    assert no_match['message'] == f'None of the 4 strategies ranked for {DEFAULT_PERIOD} match query/strategy_type.'

    jesse_trade.strategies = []
    empty = tools['browse_strategy_catalog']()
    assert empty['status'] == 'success'
    assert empty['pagination']['total_ranked_in_period'] == 0
    assert 'has no ranked strategies' in empty['message']


def test_browse_without_license_token_is_an_explicit_guest_listing(tools, jesse_trade, monkeypatch):
    monkeypatch.delitem(auth_controller.ENV_VALUES, 'LICENSE_API_TOKEN')

    result = tools['browse_strategy_catalog']()

    assert result['status'] == 'success'
    assert result['jesse_trade_signed_in'] is False
    assert result['jesse_trade_auth']['error_type'] == 'license_token_missing'
    assert 'https://jesse.trade/user/api-tokens' in result['jesse_trade_auth']['message']
    assert len(result['strategies']) == 4
    assert all(strategy['code_available'] is False for strategy in result['strategies'])
    api2_index = next(r for r in jesse_trade.requests if r['path'] == '/strategies')
    assert 'Authorization' not in api2_index['headers']


def test_browse_with_a_rejected_license_token_says_so(tools, monkeypatch):
    monkeypatch.setitem(auth_controller.ENV_VALUES, 'LICENSE_API_TOKEN', 'revoked-license')

    result = tools['browse_strategy_catalog']()

    assert result['status'] == 'success'
    assert result['jesse_trade_signed_in'] is False
    assert result['jesse_trade_auth']['error_type'] == 'license_token_rejected'
    assert 'invalid license API token' in result['jesse_trade_auth']['message']
    assert 'revoked-license' not in json.dumps(result)


def test_premium_account_sees_premium_code_as_importable(tools, monkeypatch):
    monkeypatch.setitem(auth_controller.ENV_VALUES, 'LICENSE_API_TOKEN', PREMIUM_LICENSE)

    result = tools['browse_strategy_catalog'](strategy_type='premium')

    assert _slugs(result) == ['mean-revert-pro']
    assert result['strategies'][0]['code_available'] is True
    _assert_no_secrets(result)


def test_wrong_dashboard_password_is_an_error_not_a_guest_listing(tools, monkeypatch):
    monkeypatch.setattr(catalog_service.mcp_config, 'JESSE_PASSWORD', 'wrong-password')

    for result in (
        tools['browse_strategy_catalog'](),
        tools['get_catalog_strategy_metrics']('trend-rider', DEFAULT_PERIOD, 'BTC-USDT', '4h'),
        tools['import_catalog_strategy']('trend-rider'),
    ):
        assert result['status'] == 'error'
        assert result['error_type'] == 'authentication_failed'
        _assert_no_secrets(result)


def test_jesse_trade_outage_is_an_error_not_an_empty_catalog(tools, jesse_trade):
    jesse_trade.down = True

    result = tools['browse_strategy_catalog']()

    assert result['status'] == 'error'
    assert result['error_type'] == 'jesse_trade_unavailable'
    assert 'Error connecting to jesse.trade' in result['message']
    assert 'strategies' not in result


def test_unreachable_jesse_api_is_a_connection_error(tools, monkeypatch):
    def unreachable(*args, **kwargs):
        raise requests.exceptions.ConnectionError('connection refused')

    monkeypatch.setattr(requests, 'request', unreachable)

    for result in (
        tools['browse_strategy_catalog'](),
        tools['get_catalog_strategy_metrics']('trend-rider', DEFAULT_PERIOD, 'BTC-USDT', '4h'),
        tools['import_catalog_strategy']('trend-rider'),
    ):
        assert result['status'] == 'error'
        assert result['error_type'] == 'connection_error'
        assert 'connection refused' in result['message']


def test_metrics_for_another_symbol_and_timeframe(tools, network):
    result = tools['get_catalog_strategy_metrics'](' trend-rider ', DEFAULT_PERIOD, 'eth-usdt', '1h')

    assert result['status'] == 'success'
    assert result['slug'] == 'trend-rider'
    assert (result['period'], result['symbol'], result['timeframe']) == (DEFAULT_PERIOD, 'ETH-USDT', '1h')
    assert result['metrics']['symbol'] == 'ETH-USDT'
    assert result['metrics']['expectancy'] == 1.2
    for omitted in catalog_service._OMITTED_METRICS:
        assert omitted not in result['metrics']
    # Metrics are public, so no jesse.trade session is created for them.
    assert all(call['path'] != '/auth/jesse-trade-token' for call in network)
    assert all('X-Jesse-Trade-Token' not in call['headers'] for call in network)


def test_metrics_errors_are_explicit(tools, network):
    untested = tools['get_catalog_strategy_metrics']('trend-rider', DEFAULT_PERIOD, 'SOL-USDT', '4h')
    assert untested['error_type'] == 'not_found'
    assert 'strategy metrics not found' in untested['message']
    assert untested['symbol'] == 'SOL-USDT'

    assert tools['get_catalog_strategy_metrics']('ghost-strategy', DEFAULT_PERIOD, 'BTC-USDT', '4h')['error_type'] == 'not_found'

    calls_before = len(network)
    assert tools['get_catalog_strategy_metrics']('Bad Slug', DEFAULT_PERIOD, 'BTC-USDT', '4h')['error_type'] == 'invalid_request'
    assert tools['get_catalog_strategy_metrics']('trend-rider', ' ', 'BTC-USDT', '4h')['error_type'] == 'invalid_request'
    assert len(network) == calls_before


def test_import_saves_the_strategy_under_its_class_name(project, tools, jesse_trade):
    result = tools['import_catalog_strategy']('trend-rider')

    assert result == {
        'status': 'success',
        'action': 'catalog_strategy_imported',
        'slug': 'trend-rider',
        'local_name': 'TrendRider',
        'path': 'strategies/TrendRider',
        'dashboard_url': f'{DASHBOARD}/#/strategies/TrendRider',
        'message': result['message'],
    }
    assert 'read_strategy' in result['message']
    assert (project / 'strategies' / 'TrendRider' / '__init__.py').read_text() == _code('TrendRider')
    api2_fetch = next(r for r in jesse_trade.requests if r['path'] == '/strategies/trend-rider')
    assert api2_fetch['headers']['Authorization'] == 'Bearer session-free'
    _assert_no_secrets(result)

    # The imported strategy is now a local strategy, readable by the local strategy tools.
    local = tools['read_strategy']('TrendRider')
    assert local['status'] == 'success'
    assert local['content'] == _code('TrendRider')


def test_importing_over_an_existing_local_strategy_changes_nothing(project, tools):
    existing = project / 'strategies' / 'TrendRider' / '__init__.py'
    existing.parent.mkdir()
    existing.write_text('# my own TrendRider\n')

    result = tools['import_catalog_strategy']('trend-rider')

    assert result['status'] == 'error'
    assert result['error_type'] == 'strategy_exists'
    assert result['local_name'] == 'TrendRider'
    assert 'Nothing was changed' in result['message']
    assert existing.read_text() == '# my own TrendRider\n'
    assert sorted(p.name for p in (project / 'strategies').iterdir()) == ['TrendRider']


def test_premium_import_needs_a_premium_plan(project, tools, monkeypatch):
    denied = tools['import_catalog_strategy']('mean-revert-pro')

    assert denied['error_type'] == 'strategy_access_denied'
    assert 'https://jesse.trade/pricing' in denied['message']
    assert list((project / 'strategies').iterdir()) == []

    monkeypatch.setitem(auth_controller.ENV_VALUES, 'LICENSE_API_TOKEN', PREMIUM_LICENSE)
    imported = tools['import_catalog_strategy']('mean-revert-pro')

    assert imported['status'] == 'success'
    assert imported['local_name'] == 'MeanRevertPro'
    _assert_no_secrets(imported)


@pytest.mark.parametrize(('license_token', 'error_type'), [
    (None, 'license_token_missing'),
    ('', 'license_token_missing'),
    ('revoked-license', 'license_token_rejected'),
])
def test_import_without_a_valid_license_stops_before_downloading(project, tools, jesse_trade, monkeypatch,
                                                                 license_token, error_type):
    if license_token is None:
        monkeypatch.delitem(auth_controller.ENV_VALUES, 'LICENSE_API_TOKEN')
    else:
        monkeypatch.setitem(auth_controller.ENV_VALUES, 'LICENSE_API_TOKEN', license_token)

    result = tools['import_catalog_strategy']('trend-rider')

    assert result['status'] == 'error'
    assert result['error_type'] == error_type
    assert result['slug'] == 'trend-rider'
    assert 'LICENSE_API_TOKEN' in result['message']
    assert not any(r['path'].startswith('/strategies/') for r in jesse_trade.requests)
    assert list((project / 'strategies').iterdir()) == []


def test_import_reports_unknown_malformed_and_classless_strategies(project, tools, network):
    missing = tools['import_catalog_strategy']('ghost-strategy')
    assert missing['error_type'] == 'catalog_strategy_not_found'
    assert missing['slug'] == 'ghost-strategy'

    classless = tools['import_catalog_strategy']('no-class-here')
    assert classless['error_type'] == 'invalid_request'
    assert 'No Python class definition' in classless['message']

    calls_before = len(network)
    for slug in ('Trend Rider', '../etc', 'ab', 'x' * 151):
        assert tools['import_catalog_strategy'](slug)['error_type'] == 'invalid_request'
    assert len(network) == calls_before
    assert list((project / 'strategies').iterdir()) == []


def test_agent_rules_and_resource_describe_the_catalog_workflow():
    rules = _load_packaged_rules()

    assert 'browse_strategy_catalog' in rules
    assert 'import_catalog_strategy' in rules
    assert 'jesse://strategy_catalog' in rules

    mcp = FakeMCP()
    register_resources(mcp)
    guide = mcp.resources['jesse://strategy_catalog']()
    for tool in ('browse_strategy_catalog', 'get_catalog_strategy_metrics', 'import_catalog_strategy'):
        assert f'### {tool}(' in guide
    assert 'local_name' in guide
    # The rules and guide must keep catalog tools apart from the local strategy tools.
    assert 'they are not the strategies installed in this Jesse project' in ' '.join(guide.split())
