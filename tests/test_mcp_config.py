import json
from types import SimpleNamespace

import pytest

import jesse.mcp.tools.services.config as config_service
from jesse.mcp.tools.services import backtest as backtest_service
from jesse.mcp.tools.services import monte_carlo as monte_carlo_service
from jesse.mcp.tools.services import optimization as optimization_service
from jesse.mcp.tools.services import significance_test as significance_test_service
from jesse.mcp.tools.services.session_config import (
    backtest_engine_config,
    resolve_session_run_config,
)


class _SuccessfulResponse:
    status_code = 200
    text = ''


def _spot_config(mode: str, exchange: str, overrides: dict | None = None) -> dict:
    return resolve_session_run_config({}, mode, exchange, overrides)


def test_update_config_unwraps_get_config_envelope(monkeypatch):
    captured_request = {}

    def fake_post(url, **kwargs):
        captured_request['url'] = url
        captured_request.update(kwargs)
        return _SuccessfulResponse()

    monkeypatch.setattr(config_service.mcp_config, 'JESSE_API_URL', 'http://jesse.test')
    monkeypatch.setattr(config_service.mcp_config, 'JESSE_PASSWORD', 'test-password')
    monkeypatch.setattr('requests.post', fake_post)

    result = config_service.update_config_service(json.dumps({
        'data': {
            'backtest': {
                'exchanges': {
                    'Binance Perpetual Futures': {'fee': 0}
                }
            }
        }
    }))

    assert result == {
        'status': 'success',
        'message': 'Configuration updated successfully'
    }
    assert captured_request['url'] == 'http://jesse.test/config/update'
    assert captured_request['json'] == {
        'current_config': {
            'backtest': {
                'exchanges': {
                    'Binance Perpetual Futures': {'fee': 0}
                }
            }
        }
    }


def test_update_config_preserves_direct_partial_payload(monkeypatch):
    captured_request = {}

    def fake_post(_url, **kwargs):
        captured_request.update(kwargs)
        return _SuccessfulResponse()

    monkeypatch.setattr(config_service.mcp_config, 'JESSE_PASSWORD', 'test-password')
    monkeypatch.setattr('requests.post', fake_post)

    result = config_service.update_config_service(json.dumps({
        'backtest': {'warm_up_candles': 300}
    }))

    assert result['status'] == 'success'
    assert captured_request['json'] == {
        'current_config': {
            'backtest': {'warm_up_candles': 300}
        }
    }


def test_session_config_uses_exchange_saved_defaults_and_explicit_overrides():
    settings = {
        'optimization': {
            'warm_up_candles': 300,
            'exchange': {'balance': 8_000},
            'ratio': 'sharpe',
        },
        'session_defaults': {
            'optimization': {
                'fallback': {
                    'warm_up_candles': 400,
                    'exchange': {'balance': 9_000},
                },
                'by_exchange': {
                    'Binance Spot': {
                        'warm_up_candles': 500,
                        'exchange': {
                            'balance': 12_000,
                            'type': 'futures',
                            'futures_leverage': 20,
                        },
                    }
                },
            }
        },
    }

    config = resolve_session_run_config(
        settings,
        'optimization',
        'Binance Spot',
        {'warm_up_candles': 600},
    )

    assert config['warm_up_candles'] == 600
    assert set(config) == {
        'objective_function',
        'warm_up_candles',
        'trials',
        'cpu_cores',
        'best_candidates_count',
        'exchange',
    }
    assert config['exchange'] == {
        'name': 'Binance Spot',
        'type': 'spot',
        'balance': 12_000,
        'fee': 0.001,
    }

    significance = resolve_session_run_config(
        {'significance_test': {'cpu_cores': 8, 'warm_up_candles': 123}},
        'significance_test',
        'Binance Spot',
    )
    assert set(significance) == {'warm_up_candles', 'exchange'}


@pytest.mark.parametrize(
    ('service', 'creator', 'mode', 'mode_specific_key'),
    [
        (backtest_service, backtest_service.create_backtest_draft_service, 'backtest', 'logging'),
        (
            optimization_service,
            optimization_service.create_optimization_draft_service,
            'optimization',
            'objective_function',
        ),
        (
            monte_carlo_service,
            monte_carlo_service.create_monte_carlo_draft_service,
            'monte_carlo',
            'cpu_cores',
        ),
        (
            significance_test_service,
            significance_test_service.create_significance_test_draft_service,
            'significance_test',
            'warm_up_candles',
        ),
    ],
)
def test_mcp_drafts_store_session_owned_config(
    monkeypatch,
    service,
    creator,
    mode,
    mode_specific_key,
):
    route = json.dumps([
        {
            'exchange': 'Binance Spot',
            'strategy': 'ExampleStrategy',
            'symbol': 'BTC-USDT',
            'timeframe': '4h',
        }
    ])
    monkeypatch.setattr(service.requests, 'post', lambda *args, **kwargs: _SuccessfulResponse())
    monkeypatch.setattr(service, 'hash_password', lambda password: 'hashed')
    monkeypatch.setattr(service, 'load_session_run_config', _spot_config)

    result = creator(exchange='Binance Spot', routes=route)

    assert result['status'] == 'success'
    stored = result['draft_state']['form']['config']
    assert mode_specific_key in stored
    assert stored['exchange']['name'] == 'Binance Spot'
    assert stored['exchange']['type'] == 'spot'
    assert 'futures_leverage' not in stored['exchange']
    assert 'futures_leverage_mode' not in stored['exchange']


def test_backtest_engine_config_keeps_the_session_exchange_snapshot():
    stored = _spot_config(
        'backtest',
        'Binance Spot',
        {
            'warm_up_candles': 321,
            'exchange': {'balance': 5_000, 'fee': 0.002},
        },
    )

    engine = backtest_engine_config(stored)

    assert engine['warm_up_candles'] == 321
    assert engine['exchanges'] == {
        'Binance Spot': {
            'name': 'Binance Spot',
            'type': 'spot',
            'balance': 5_000,
            'fee': 0.002,
        }
    }


def test_optimization_launch_migrates_flat_draft_config(monkeypatch):
    form = {
        'exchange': 'Binance Spot',
        'routes': [],
        'data_routes': [],
        'objective_function': 'calmar',
        'trials': 17,
        'best_candidates_count': 4,
        'warm_up_candles': 345,
        'cpu_cores': 3,
    }
    state = {'form': form, 'results': {}}
    monkeypatch.setattr(optimization_service, 'load_session_run_config', _spot_config)

    payload = optimization_service._build_run_payload('optimization-id', form, state)

    stored = payload['state']['form']['config']
    assert stored['objective_function'] == 'calmar'
    assert stored['trials'] == 17
    assert stored['best_candidates_count'] == 4
    assert stored['warm_up_candles'] == 345
    assert stored['cpu_cores'] == 3
    assert 'futures_leverage' not in stored['exchange']
    assert payload['cpu_cores'] == 3
    assert payload['config']['exchange']['type'] == 'spot'
    assert payload['config']['exchange']['futures_leverage'] == 1
    assert payload['config']['exchange']['futures_leverage_mode'] == 'cross'


def test_monte_carlo_launch_migrates_flat_draft_config(monkeypatch):
    form = {
        'exchange': 'Binance Spot',
        'routes': [],
        'data_routes': [],
        'warm_up_candles': 456,
        'cpu_cores': 2,
    }
    state = {'form': form, 'results': {}}
    monkeypatch.setattr(monte_carlo_service, 'load_session_run_config', _spot_config)

    payload = monte_carlo_service._build_run_payload('monte-carlo-id', form, state)

    stored = payload['state']['form']['config']
    assert stored['warm_up_candles'] == 456
    assert stored['cpu_cores'] == 2
    assert stored['exchange']['type'] == 'spot'
    assert payload['cpu_cores'] == 2
    assert payload['config']['starting_balance'] == stored['exchange']['balance']
    assert payload['config']['fee'] == stored['exchange']['fee']


def test_significance_test_launch_migrates_draft_config(monkeypatch):
    state = {
        'form': {
            'exchange': 'Binance Spot',
            'routes': [
                {
                    'exchange': 'Binance Spot',
                    'strategy': 'ExampleStrategy',
                    'symbol': 'BTC-USDT',
                    'timeframe': '4h',
                }
            ],
            'data_routes': [],
            'start_date': '2024-01-01',
            'finish_date': '2024-03-01',
        },
        'results': {},
    }
    launch_payload = {}

    def post(url, **kwargs):
        if url.endswith('/significance-test/sessions/significance-id'):
            return SimpleNamespace(
                status_code=200,
                text='',
                json=lambda: {'session': {'state': state}},
            )
        if url.endswith('/significance-test'):
            launch_payload.update(kwargs['json'])
            return SimpleNamespace(status_code=202, text='')
        raise AssertionError(f'Unexpected MCP request: {url}')

    monkeypatch.setattr(significance_test_service, 'hash_password', lambda password: 'hashed')
    monkeypatch.setattr(significance_test_service.requests, 'post', post)
    monkeypatch.setattr(significance_test_service, 'load_session_run_config', _spot_config)

    result = significance_test_service.run_significance_test_service('significance-id')

    assert result['status'] == 'started'
    assert launch_payload['state'] is state
    assert launch_payload['config'] is state['form']['config']
    assert launch_payload['config']['exchange']['type'] == 'spot'
    assert 'futures_leverage' not in launch_payload['config']['exchange']
