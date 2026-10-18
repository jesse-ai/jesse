"""Run settings of the MCP research drafts: named arguments, config_overrides, where each value
came from, the warnings, and partial updates of a stored draft."""
import json
from types import SimpleNamespace

import pytest

from jesse.mcp.tools.services import backtest as backtest_service
from jesse.mcp.tools.services import draft_config
from jesse.mcp.tools.services import monte_carlo as monte_carlo_service
from jesse.mcp.tools.services import optimization as optimization_service
from jesse.mcp.tools.services import session_config
from jesse.mcp.tools.services import significance_test as significance_test_service
from jesse.mcp.tools.services.session_config import (
    parse_draft_config_arguments,
    resolve_draft_run_config,
)

FUTURES = 'Binance Perpetual Futures'
SPOT = 'Binance Spot'

# The Dashboard keeps separate defaults per mode and exchange; this mirrors a project whose
# backtests on the futures exchange were set to 0.0002 / 20x while optimizations kept 0.0006 / 5x.
SAVED = {
    'session_defaults': {
        'backtest': {'by_exchange': {FUTURES: {'exchange': {'fee': 0.0002, 'futures_leverage': 20}}}},
        'optimization': {
            'by_exchange': {FUTURES: {'trials': 30, 'cpu_cores': 1, 'exchange': {'fee': 0.0006, 'futures_leverage': 5}}},
        },
    },
}


def _route(exchange: str = FUTURES) -> str:
    return json.dumps([{'exchange': exchange, 'strategy': 'ExampleStrategy', 'symbol': 'BTC-USDT', 'timeframe': '4h'}])


class _Ok:
    status_code = 200
    text = ''


@pytest.fixture
def saved_settings(monkeypatch):
    settings = {}
    monkeypatch.setattr(session_config, 'load_saved_settings', lambda: settings)
    return settings


# ---------------------------------------------------------------------------
# Resolving and describing a draft's run config
# ---------------------------------------------------------------------------

def test_named_arguments_win_over_saved_defaults_and_config_overrides():
    overrides, warnings = parse_draft_config_arguments(
        'optimization', FUTURES,
        json.dumps({'trials': 12, 'exchange': {'fee': 0.001, 'balance': 5_000}}),
        fee=0.0002, leverage=20,
    )
    resolved = resolve_draft_run_config('optimization', FUTURES, overrides, settings=SAVED)

    exchange = resolved['config']['exchange']
    assert (exchange['fee'], exchange['futures_leverage'], exchange['balance']) == (0.0002, 20, 5_000)
    assert resolved['config']['trials'] == 12
    assert resolved['config_source']['exchange.fee'] == 'explicit'
    assert resolved['config_source']['exchange.futures_leverage'] == 'explicit'
    assert resolved['config_source']['trials'] == 'explicit'
    assert resolved['config_source']['cpu_cores'] == 'saved_default'
    assert warnings == [] and resolved['warnings'] == []


def test_sources_tell_saved_exchange_and_built_in_defaults_apart():
    resolved = resolve_draft_run_config('backtest', SPOT, {}, settings={})

    assert resolved['config_source']['exchange.fee'] == 'exchange_default'
    assert resolved['config_source']['exchange.balance'] == 'hard_default'
    assert 'exchange.futures_leverage' not in resolved['config_source']

    futures = resolve_draft_run_config('backtest', FUTURES, {}, settings=SAVED)
    assert futures['config_source']['exchange.fee'] == 'saved_default'
    assert futures['config']['exchange']['fee'] == 0.0002


def test_tool_defaults_beat_saved_defaults_but_not_the_agent():
    kept = resolve_draft_run_config('optimization', FUTURES, {}, settings=SAVED, tool_defaults={'cpu_cores': 4})
    assert kept['config']['cpu_cores'] == 4
    assert kept['config_source']['cpu_cores'] == 'tool_default'

    chosen = resolve_draft_run_config(
        'optimization', FUTURES, {'cpu_cores': 2}, settings=SAVED, tool_defaults={'cpu_cores': 4},
    )
    assert chosen['config']['cpu_cores'] == 2
    assert chosen['config_source']['cpu_cores'] == 'explicit'


def test_built_in_leverage_is_flagged():
    resolved = resolve_draft_run_config('backtest', FUTURES, {}, settings={})

    assert resolved['config_source']['exchange.futures_leverage'] == 'hard_default'
    assert any(warning.startswith('leverage 1 is Jesse\'s built-in default') for warning in resolved['warnings'])


def test_mode_defaults_that_differ_from_backtest_defaults_are_flagged():
    resolved = resolve_draft_run_config('optimization', FUTURES, {}, settings=SAVED)

    assert resolved['config']['exchange']['fee'] == 0.0006
    assert resolved['warnings'] == [
        'The saved optimization defaults on Binance Perpetual Futures differ from its backtest defaults: '
        'fee 0.0006 (backtests: 0.0002), leverage 5 (backtests: 20). Pass fee= and leverage= to choose explicitly.'
    ]

    explicit, _ = parse_draft_config_arguments('optimization', FUTURES, fee=0.0002, leverage=20)
    assert resolve_draft_run_config('optimization', FUTURES, explicit, settings=SAVED)['warnings'] == []


def test_leverage_is_dropped_with_a_warning_on_a_spot_exchange():
    overrides, warnings = parse_draft_config_arguments('backtest', SPOT, fee=0.001, leverage=10, leverage_mode='cross')

    assert overrides == {'exchange': {'fee': 0.001}}
    assert warnings == ['leverage and leverage_mode ignored: Binance Spot is a spot exchange.']


@pytest.mark.parametrize(('mode', 'kwargs', 'message'), [
    ('backtest', {'fee': -0.1}, 'fee must be at least 0'),
    ('backtest', {'fee': 1.5}, 'fee must be below 1'),
    ('backtest', {'fee': True}, 'fee must be a number'),
    ('backtest', {'leverage': 2.5}, 'leverage must be a whole number'),
    ('backtest', {'leverage': 0}, 'leverage must be at least 1'),
    ('backtest', {'balance': 0}, 'balance must be more than 0'),
    ('backtest', {'warm_up_candles': -1}, 'warm_up_candles must be at least 0'),
    ('backtest', {'leverage_mode': 'portfolio'}, 'leverage_mode must be one of: cross, isolated'),
    ('backtest', {'config_overrides': '{"trials": 5}'}, 'backtest drafts do not use: trials'),
    ('backtest', {'config_overrides': '{"exchange": {"name": "Other"}}'}, 'config_overrides.exchange cannot set: name'),
    ('backtest', {'config_overrides': '[1]'}, 'config_overrides must be a JSON object'),
    ('backtest', {'config_overrides': '{oops'}, 'config_overrides is not valid JSON'),
    ('backtest', {'config_overrides': {'logging': {'trading_candles': 'yes'}}}, 'config_overrides.logging must map'),
    ('optimization', {'config_overrides': {'objective_function': 'profit'}}, 'objective_function must be one of'),
    ('optimization', {'config_overrides': {'trials': 0}}, 'config_overrides.trials must be at least 1'),
    ('significance_test', {'config_overrides': {'cpu_cores': 2}}, 'significance_test drafts do not use: cpu_cores'),
])
def test_invalid_run_settings_are_refused_with_a_message(mode, kwargs, message):
    config_overrides = kwargs.pop('config_overrides', None)
    with pytest.raises(ValueError, match=message.replace('(', r'\(')):
        parse_draft_config_arguments(mode, FUTURES, config_overrides, **kwargs)


def test_leverage_mode_must_be_one_the_exchange_supports():
    with pytest.raises(ValueError, match='must be one of: cross'):
        parse_draft_config_arguments('backtest', 'Apex Omni Perpetual', leverage_mode='isolated')


# ---------------------------------------------------------------------------
# Create tools
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(('service', 'creator', 'mode'), [
    (backtest_service, backtest_service.create_backtest_draft_service, 'backtest'),
    (optimization_service, optimization_service.create_optimization_draft_service, 'optimization'),
    (monte_carlo_service, monte_carlo_service.create_monte_carlo_draft_service, 'monte_carlo'),
    (significance_test_service, significance_test_service.create_significance_test_draft_service, 'significance_test'),
])
def test_every_create_tool_stores_the_requested_run_settings(monkeypatch, saved_settings, service, creator, mode):
    saved_settings.update(SAVED)
    monkeypatch.setattr(service.requests, 'post', lambda *args, **kwargs: _Ok())
    monkeypatch.setattr(service, 'hash_password', lambda password: 'hashed')

    result = creator(
        exchange=FUTURES, routes=_route(), fee=0.0002, leverage=20, leverage_mode='isolated',
        balance=25_000, warm_up_candles=300,
    )

    assert result['status'] == 'success', result
    stored = result['draft_state']['form']['config']
    assert stored == result['run_config']
    assert stored['exchange'] == {
        'name': FUTURES, 'type': 'futures', 'balance': 25_000, 'fee': 0.0002,
        'futures_leverage_mode': 'isolated', 'futures_leverage': 20,
    }
    assert stored['warm_up_candles'] == 300
    for field in ('exchange.fee', 'exchange.futures_leverage', 'exchange.futures_leverage_mode',
                  'exchange.balance', 'warm_up_candles'):
        assert result['config_source'][field] == 'explicit'
    assert 'config_warnings' not in result


@pytest.mark.parametrize(('service', 'creator'), [
    (backtest_service, backtest_service.create_backtest_draft_service),
    (optimization_service, optimization_service.create_optimization_draft_service),
    (monte_carlo_service, monte_carlo_service.create_monte_carlo_draft_service),
    (significance_test_service, significance_test_service.create_significance_test_draft_service),
])
def test_an_invalid_run_setting_creates_nothing(monkeypatch, saved_settings, service, creator):
    posts = []
    monkeypatch.setattr(service.requests, 'post', lambda *args, **kwargs: posts.append(args) or _Ok())
    monkeypatch.setattr(service, 'hash_password', lambda password: 'hashed')

    result = creator(exchange=FUTURES, routes=_route(), leverage=0)

    assert result == {'status': 'error', 'message': 'leverage must be at least 1.'}
    assert posts == []


def test_optimization_draft_uses_saved_defaults_for_omitted_settings(monkeypatch, saved_settings):
    saved_settings.update(SAVED)
    monkeypatch.setattr(optimization_service.requests, 'post', lambda *args, **kwargs: _Ok())
    monkeypatch.setattr(optimization_service, 'hash_password', lambda password: 'hashed')
    monkeypatch.setattr(optimization_service, 'default_cpu_cores', lambda: 3)

    result = optimization_service.create_optimization_draft_service(exchange=FUTURES, routes=_route())

    assert result['run_config']['trials'] == 30
    assert result['config_source']['trials'] == 'saved_default'
    # Unattended MCP runs keep their own worker count instead of the saved one.
    assert result['run_config']['cpu_cores'] == 3
    assert result['config_source']['cpu_cores'] == 'tool_default'
    assert result['config_warnings'][0].startswith('The saved optimization defaults on')

    chosen = optimization_service.create_optimization_draft_service(
        exchange=FUTURES, routes=_route(), trials=8, cpu_cores=2, objective_function='calmar',
    )
    assert (chosen['run_config']['trials'], chosen['run_config']['cpu_cores']) == (8, 2)
    assert chosen['run_config']['objective_function'] == 'calmar'
    assert chosen['config_source']['cpu_cores'] == 'explicit'


def test_backtest_run_sends_the_fee_the_draft_was_created_with(monkeypatch, saved_settings):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith('/backtest/update-state') or url.endswith('/notes'):
            return _Ok()
        if url.endswith('/backtest/sessions/draft-id'):
            state = calls[0][1]['json']['state']
            return SimpleNamespace(status_code=200, text='', json=lambda: {'session': {'state': state}})
        if url.endswith('/backtest'):
            return SimpleNamespace(status_code=202, text='')
        raise AssertionError(url)

    monkeypatch.setattr(backtest_service.requests, 'post', post)
    monkeypatch.setattr(backtest_service, 'hash_password', lambda password: 'hashed')
    monkeypatch.setattr(backtest_service.uuid, 'uuid4', lambda: 'draft-id')
    saved_settings.update(SAVED)

    backtest_service.create_backtest_draft_service(exchange=FUTURES, routes=_route(), fee=0.0003, leverage=7)
    started = backtest_service.run_backtest_service('draft-id')

    assert started['status'] == 'started'
    engine_exchange = calls[-1][1]['json']['config']['exchanges'][FUTURES]
    assert (engine_exchange['fee'], engine_exchange['futures_leverage']) == (0.0003, 7)


# ---------------------------------------------------------------------------
# Partial updates
# ---------------------------------------------------------------------------

def _stored_draft(status: str = 'draft') -> dict:
    return {
        'status': status,
        'state': json.dumps({
            'form': {
                'exchange': FUTURES,
                'routes': json.loads(_route()),
                'start_date': '2024-01-01',
                'config': session_config.resolve_session_run_config(
                    {}, 'backtest', FUTURES, {'warm_up_candles': 400, 'exchange': {'fee': 0.0005}},
                ),
            },
            'results': {'showResults': False},
        }),
    }


@pytest.fixture
def stored_backtest(monkeypatch, saved_settings):
    calls = []
    session = {'value': _stored_draft()}

    def post(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith('/backtest/sessions/draft-id'):
            return SimpleNamespace(status_code=200, text='', json=lambda: {'session': session['value']})
        if url.endswith('/backtest/update-state'):
            return _Ok()
        raise AssertionError(url)

    monkeypatch.setattr(draft_config.requests, 'post', post)
    monkeypatch.setattr(draft_config, 'hash_password', lambda password: 'hashed')
    return SimpleNamespace(calls=calls, session=session)


def test_partial_update_changes_only_the_given_run_settings(stored_backtest):
    result = backtest_service.update_backtest_draft_service('draft-id', leverage=20)

    assert result['status'] == 'success', result
    assert result['backtest_id'] == 'draft-id'
    saved_url, saved = stored_backtest.calls[-1]
    assert saved_url.endswith('/backtest/update-state')
    form = saved['json']['state']['form']
    assert form['routes'] == json.loads(_route())
    assert form['start_date'] == '2024-01-01'
    assert saved['json']['state']['results'] == {'showResults': False}
    assert form['config']['exchange']['futures_leverage'] == 20
    assert form['config']['exchange']['fee'] == 0.0005
    assert form['config']['warm_up_candles'] == 400
    assert result['config_source']['exchange.futures_leverage'] == 'explicit'
    assert result['config_source']['exchange.fee'] == 'stored'


def test_partial_update_refuses_a_session_that_already_ran(stored_backtest):
    stored_backtest.session['value'] = _stored_draft('finished')

    result = backtest_service.update_backtest_draft_service('draft-id', fee=0.0001)

    assert result['status'] == 'error'
    assert 'is finished, not a draft' in result['message']
    assert not any(url.endswith('/update-state') for url, _ in stored_backtest.calls)


def test_partial_update_reports_invalid_settings_without_saving(stored_backtest):
    result = backtest_service.update_backtest_draft_service('draft-id', config_overrides='{"trials": 3}')

    assert result['status'] == 'error'
    assert 'backtest drafts do not use: trials' in result['message']
    assert not any(url.endswith('/update-state') for url, _ in stored_backtest.calls)


@pytest.mark.parametrize('updater', [
    backtest_service.update_backtest_draft_service,
    optimization_service.update_optimization_draft_service,
    monte_carlo_service.update_monte_carlo_draft_service,
    significance_test_service.update_significance_test_draft_service,
])
def test_update_needs_exactly_one_of_state_or_run_settings(updater):
    both = updater('draft-id', state='{"form": {}}', fee=0.0002)
    neither = updater('draft-id')

    assert both['status'] == 'error' and 'not both' in both['message']
    assert neither['status'] == 'error' and 'Nothing to update' in neither['message']


@pytest.mark.parametrize(('updater', 'api_path', 'id_key'), [
    (optimization_service.update_optimization_draft_service, 'optimization', 'session_id'),
    (monte_carlo_service.update_monte_carlo_draft_service, 'monte-carlo', 'session_id'),
    (significance_test_service.update_significance_test_draft_service, 'significance-test', 'session_id'),
])
def test_partial_update_uses_each_modes_routes(monkeypatch, saved_settings, updater, api_path, id_key):
    urls = []
    state = {'form': {'exchange': FUTURES, 'config': {'exchange': {'fee': 0.0005}}}}

    def post(url, **kwargs):
        urls.append(url)
        if url.endswith(f'/{api_path}/sessions/draft-id'):
            return SimpleNamespace(status_code=200, text='', json=lambda: {'session': {'status': 'draft', 'state': state}})
        return _Ok()

    monkeypatch.setattr(draft_config.requests, 'post', post)
    monkeypatch.setattr(draft_config, 'hash_password', lambda password: 'hashed')

    result = updater('draft-id', fee=0.0001)

    assert result['status'] == 'success', result
    assert result[id_key] == 'draft-id'
    assert result['run_config']['exchange']['fee'] == 0.0001
    assert urls[-1].endswith(f'/{api_path}/update-state')


def test_named_mode_arguments_also_win_over_config_overrides(monkeypatch, saved_settings):
    monkeypatch.setattr(optimization_service.requests, 'post', lambda *args, **kwargs: _Ok())
    monkeypatch.setattr(optimization_service, 'hash_password', lambda password: 'hashed')

    result = optimization_service.create_optimization_draft_service(
        exchange=FUTURES, routes=_route(), trials=50, config_overrides='{"trials": 300, "best_candidates_count": 7}',
    )

    assert (result['run_config']['trials'], result['run_config']['best_candidates_count']) == (50, 7)
