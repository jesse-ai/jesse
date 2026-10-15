from copy import deepcopy
from importlib import import_module
import sys

import numpy as np
import pytest
import ray

from jesse import research
from jesse.candle_pipelines import MovingBlockBootstrapCandlesPipeline
from jesse.config import config
from jesse.factories import candles_from_close_prices
import jesse.helpers as jh
from jesse.routes import router
from jesse.store import store


def _monte_carlo_inputs(strategy: str = 'TestOptimizationIsolation') -> tuple[dict, list, dict]:
    exchange = 'Monte Carlo Isolation Exchange'
    symbol = 'TEST-USDT'
    config_input = {
        'starting_balance': 10_000,
        'fee': 0,
        'type': 'futures',
        'futures_leverage': 1,
        'futures_leverage_mode': 'cross',
        'exchange': exchange,
        'warm_up_candles': 0,
    }
    routes = [{
        'exchange': exchange,
        'strategy': strategy,
        'symbol': symbol,
        'timeframe': '1m',
    }]

    # Non-uniform but upward-biased changes let the seeded candle bootstrap
    # produce distinct, reproducible market paths without invalid prices.
    changes = (1.5, -0.75, 2.25, -1.0, 0.5, -0.25)
    prices = [100.0]
    for index in range(319):
        prices.append(prices[-1] + changes[index % len(changes)])

    candles = {
        jh.key(exchange, symbol): {
            'exchange': exchange,
            'symbol': symbol,
            'candles': candles_from_close_prices(prices),
        },
    }
    return config_input, routes, candles


def _assert_inputs_unchanged(
    config_input: dict,
    routes: list,
    candles: dict,
    expected_config: dict,
    expected_routes: list,
    expected_candles: dict,
) -> None:
    assert config_input == expected_config
    assert routes == expected_routes
    assert candles.keys() == expected_candles.keys()
    for key, candle_set in candles.items():
        assert candle_set['exchange'] == expected_candles[key]['exchange']
        assert candle_set['symbol'] == expected_candles[key]['symbol']
        assert np.array_equal(candle_set['candles'], expected_candles[key]['candles'])


def _assert_research_runtime_is_clean(ray_was_initialized: bool) -> None:
    assert ray.is_initialized() is ray_was_initialized
    assert config['app']['trading_mode'] == ''
    assert router.routes == []
    assert router.data_routes == []
    api_module = sys.modules.get('jesse.services.api')
    if api_module is not None:
        assert api_module.api.drivers == {}
    assert store.vars == {}
    assert store.exchanges.storage == {}
    assert store.orders.storage == {}
    assert jh.is_live() is False
    assert jh.is_optimizing() is False


def _trade_scenario_fingerprint(result: dict) -> list:
    return [
        {
            'scenario_index': scenario['scenario_index'],
            'trade_order': [trade['opened_at'] for trade in scenario['trades']],
            'max_drawdown': round(scenario['max_drawdown'], 10),
            'sharpe_ratio': round(scenario['sharpe_ratio'], 10),
            'final_value': round(scenario['final_value'], 10),
        }
        for scenario in result['scenarios']
    ]


def _candle_scenario_fingerprint(result: dict) -> list:
    return [
        {
            'scenario_index': scenario['scenario_index'],
            'total': scenario['metrics']['total'],
            'net_profit_percentage': round(scenario['metrics']['net_profit_percentage'], 10),
            'finishing_balance': round(scenario['metrics']['finishing_balance'], 10),
            'opened_at': [trade['opened_at'] for trade in scenario.get('trades', [])],
        }
        for scenario in result['scenarios']
    ]


@pytest.mark.slow
def test_trade_monte_carlo_is_deterministic_and_isolated() -> None:
    config_input, routes, candles = _monte_carlo_inputs()
    expected_config = deepcopy(config_input)
    expected_routes = deepcopy(routes)
    expected_candles = deepcopy(candles)
    ray_was_initialized = ray.is_initialized()

    baseline = research.backtest(
        config_input,
        routes,
        [],
        candles,
        fast_mode=True,
        hyperparameters={'entry_interval': 4},
    )
    assert baseline['metrics']['total'] > 5

    progress_updates = []
    streamed_results = []
    first = research.monte_carlo_trades(
        config_input,
        routes,
        [],
        candles,
        hyperparameters={'entry_interval': 4},
        num_scenarios=4,
        cpu_cores=2,
        progress_callback=progress_updates.append,
        result_callback=streamed_results.append,
    )
    second = research.monte_carlo_trades(
        config_input,
        routes,
        [],
        candles,
        hyperparameters={'entry_interval': 4},
        num_scenarios=4,
        cpu_cores=2,
    )

    assert first['num_scenarios'] == first['total_requested'] == 4
    assert first['confidence_analysis']['summary']['num_simulations'] == 4
    assert [scenario['scenario_index'] for scenario in first['scenarios']] == [0, 1, 2, 3]
    assert progress_updates == [1, 2, 3, 4]
    assert len(streamed_results) == 4
    assert _trade_scenario_fingerprint(first) == _trade_scenario_fingerprint(second)
    assert len({tuple(item['trade_order']) for item in _trade_scenario_fingerprint(first)}) > 1
    _assert_inputs_unchanged(
        config_input,
        routes,
        candles,
        expected_config,
        expected_routes,
        expected_candles,
    )
    _assert_research_runtime_is_clean(ray_was_initialized)


@pytest.mark.slow
def test_candle_monte_carlo_returns_every_requested_seeded_scenario() -> None:
    config_input, routes, candles = _monte_carlo_inputs()
    expected_config = deepcopy(config_input)
    expected_routes = deepcopy(routes)
    expected_candles = deepcopy(candles)
    ray_was_initialized = ray.is_initialized()
    pipeline_kwargs = {'batch_size': 320, 'seed': 42}

    baseline = research.backtest(
        config_input,
        routes,
        [],
        candles,
        fast_mode=True,
        hyperparameters={'entry_interval': 4},
    )
    assert baseline['metrics']['total'] > 5

    progress_updates = []
    streamed_results = []
    first = research.monte_carlo_candles(
        config_input,
        routes,
        [],
        candles,
        hyperparameters={'entry_interval': 4},
        num_scenarios=3,
        cpu_cores=2,
        candles_pipeline_class=MovingBlockBootstrapCandlesPipeline,
        candles_pipeline_kwargs=pipeline_kwargs,
        progress_callback=progress_updates.append,
        result_callback=streamed_results.append,
    )
    second = research.monte_carlo_candles(
        config_input,
        routes,
        [],
        candles,
        hyperparameters={'entry_interval': 4},
        num_scenarios=3,
        cpu_cores=2,
        candles_pipeline_class=MovingBlockBootstrapCandlesPipeline,
        candles_pipeline_kwargs=pipeline_kwargs,
    )

    assert first['original'] is not None
    assert first['num_scenarios'] == first['total_requested'] == 3
    assert first['confidence_analysis']['summary']['num_simulations'] == 3
    assert [scenario['scenario_index'] for scenario in first['scenarios']] == [1, 2, 3]
    assert progress_updates == [1, 2, 3]
    assert len(streamed_results) == 3
    assert _candle_scenario_fingerprint(first) == _candle_scenario_fingerprint(second)
    assert len({
        (item['total'], item['net_profit_percentage'], tuple(item['opened_at']))
        for item in _candle_scenario_fingerprint(first)
    }) > 1
    assert pipeline_kwargs == {'batch_size': 320, 'seed': 42}
    _assert_inputs_unchanged(
        config_input,
        routes,
        candles,
        expected_config,
        expected_routes,
        expected_candles,
    )
    _assert_research_runtime_is_clean(ray_was_initialized)


def test_trade_monte_carlo_cleans_up_after_original_backtest_failure() -> None:
    config_input, routes, candles = _monte_carlo_inputs('TestEmptyStrategy')
    ray_was_initialized = ray.is_initialized()

    with pytest.raises(ValueError, match='No trades found in original backtest'):
        research.monte_carlo_trades(
            config_input,
            routes,
            [],
            candles,
            num_scenarios=2,
            cpu_cores=2,
        )

    _assert_research_runtime_is_clean(ray_was_initialized)


def test_candle_monte_carlo_cleans_up_after_original_backtest_failure() -> None:
    config_input, routes, candles = _monte_carlo_inputs()
    candle_key = next(iter(candles))
    candles[candle_key]['candles'][100, 0] = candles[candle_key]['candles'][99, 0]
    ray_was_initialized = ray.is_initialized()

    with pytest.raises(ValueError, match='strictly increasing unique timestamps'):
        research.monte_carlo_candles(
            config_input,
            routes,
            [],
            candles,
            hyperparameters={'entry_interval': 4},
            num_scenarios=2,
            cpu_cores=2,
            candles_pipeline_class=MovingBlockBootstrapCandlesPipeline,
            candles_pipeline_kwargs={'batch_size': 319, 'seed': 42},
        )

    _assert_research_runtime_is_clean(ray_was_initialized)


_SIMULATION_ENTRY_POINTS = [
    ('jesse.research.monte_carlo.monte_carlo_trades', 'monte_carlo_trades', '_run_monte_carlo_simulation'),
    ('jesse.research.monte_carlo.monte_carlo_candles', 'monte_carlo_candles', '_run_monte_carlo_candles_simulation'),
]


def _fake_ray_lifecycle(monkeypatch, module, simulation, *, initialized: bool) -> list:
    """Replace Ray's lifecycle in `module` with a recorder, so no runtime is started."""
    events = []
    state = {'initialized': initialized}

    def start(cpu_cores):
        events.append(('start', cpu_cores))
        state['initialized'] = True

    def unexpected_raw_init(**kwargs):
        raise AssertionError('Ray must be started through jesse.services.ray_runtime')

    monkeypatch.setattr(module, 'cpu_count', lambda: 8)
    monkeypatch.setattr(module, 'initialize_ray', start)
    monkeypatch.setattr(module.ray, 'init', unexpected_raw_init)
    monkeypatch.setattr(module.ray, 'is_initialized', lambda: state['initialized'])
    monkeypatch.setattr(module.ray, 'shutdown', lambda: events.append('shutdown'))
    monkeypatch.setattr(module, simulation, lambda *args: events.append('run') or 'result')
    return events


@pytest.mark.parametrize(('module_name', 'entry_point', 'simulation'), _SIMULATION_ENTRY_POINTS)
def test_monte_carlo_starts_and_releases_ray_through_the_shared_runtime(
    monkeypatch, module_name, entry_point, simulation
) -> None:
    module = import_module(module_name)
    events = _fake_ray_lifecycle(monkeypatch, module, simulation, initialized=False)

    assert getattr(module, entry_point)({}, [], [], {}, cpu_cores=3) == 'result'

    assert events == [('start', 3), 'run', 'shutdown']


@pytest.mark.parametrize(('module_name', 'entry_point', 'simulation'), _SIMULATION_ENTRY_POINTS)
def test_monte_carlo_reuses_a_caller_owned_ray_runtime(
    monkeypatch, module_name, entry_point, simulation
) -> None:
    module = import_module(module_name)
    events = _fake_ray_lifecycle(monkeypatch, module, simulation, initialized=True)

    assert getattr(module, entry_point)({}, [], [], {}, cpu_cores=3) == 'result'

    assert events == ['run']


@pytest.mark.parametrize(('module_name', 'entry_point', 'simulation'), _SIMULATION_ENTRY_POINTS)
def test_monte_carlo_reports_ray_startup_refusal_without_shutting_down(
    monkeypatch, module_name, entry_point, simulation
) -> None:
    module = import_module(module_name)
    events = _fake_ray_lifecycle(monkeypatch, module, simulation, initialized=False)

    def refuse(cpu_cores):
        raise MemoryError('Not enough available memory to start research workers.')

    monkeypatch.setattr(module, 'initialize_ray', refuse)

    with pytest.raises(RuntimeError, match='Error initializing Ray: Not enough available memory'):
        getattr(module, entry_point)({}, [], [], {}, cpu_cores=3)

    assert events == []
