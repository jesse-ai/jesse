from copy import deepcopy
import importlib

import pytest
import ray

from jesse import research
from jesse.config import config
from jesse.factories import candles_from_close_prices
import jesse.helpers as jh
from jesse.modes.optimize_mode import fitness
from jesse.routes import router
from jesse.store import store


def _optimization_inputs() -> tuple[dict, list, list, dict, dict]:
    exchange = 'Optimization Isolation Exchange'
    symbol = 'TEST-USDT'
    config_input = {
        'exchange': {
            'name': exchange,
            'balance': 10_000,
            'fee': 0,
            'type': 'futures',
            'futures_leverage': 1,
            'futures_leverage_mode': 'cross',
        },
        'warm_up_candles': 0,
    }
    routes = [{
        'strategy': 'TestOptimizationIsolation',
        'symbol': symbol,
        'timeframe': '1m',
    }]

    def candle_set(prices: range) -> dict:
        return {
            jh.key(exchange, symbol): {
                'exchange': exchange,
                'symbol': symbol,
                'candles': candles_from_close_prices(prices),
            },
        }

    return config_input, routes, [], candle_set(range(10, 170)), candle_set(range(200, 320))


def _assert_research_runtime_is_clean() -> None:
    assert config['app']['trading_mode'] == ''
    assert router.routes == []
    assert router.data_routes == []
    assert store.vars == {}
    assert store.exchanges.storage == {}
    assert store.orders.storage == {}
    assert jh.is_live() is False
    assert jh.is_optimizing() is False


@pytest.mark.slow
def test_multicore_optimization_is_isolated_from_the_next_research_run() -> None:
    config_input, routes, data_routes, training_candles, testing_candles = _optimization_inputs()
    original_routes = deepcopy(routes)
    original_data_routes = deepcopy(data_routes)
    ray_was_initialized = ray.is_initialized()

    result = research.optimize(
        config=config_input,
        routes=routes,
        data_routes=data_routes,
        training_candles=training_candles,
        training_warmup_candles={},
        testing_candles=testing_candles,
        testing_warmup_candles={},
        cpu_cores=2,
        trials=4,
        objective_function='omega',
        progress_bar=False,
    )

    assert result['completed_trials'] == 4
    assert result['total_trials'] == 4
    assert result['objective_function'] == 'omega'
    assert routes == original_routes
    assert data_routes == original_data_routes
    assert ray.is_initialized() is ray_was_initialized
    _assert_research_runtime_is_clean()

    # A regular backtest immediately after Ray finishes proves the coordinator
    # did not retain optimization mode, routes, stores, or helper caches.
    backtest_config = {
        'starting_balance': 10_000,
        'fee': 0,
        'type': 'futures',
        'futures_leverage': 1,
        'futures_leverage_mode': 'cross',
        'exchange': config_input['exchange']['name'],
        'warm_up_candles': 0,
    }
    backtest_routes = [{
        'exchange': config_input['exchange']['name'],
        **routes[0],
    }]
    backtest_result = research.backtest(
        backtest_config,
        backtest_routes,
        [],
        training_candles,
        fast_mode=True,
        hyperparameters={'entry_interval': 4},
    )

    assert backtest_result['metrics']['total'] > 5
    _assert_research_runtime_is_clean()


def test_ray_fitness_uses_explicit_worker_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    training_metrics = {
        'total': 10,
        'omega_ratio': 2,
        'sharpe_ratio': 4,
        'net_profit_percentage': 5,
        'win_rate': 0.6,
    }
    testing_metrics = {'total': 8}
    results = iter([
        {'metrics': training_metrics},
        {'metrics': testing_metrics},
    ])
    monkeypatch.setattr(fitness, 'isolated_backtest', lambda *_args, **_kwargs: next(results))

    user_config = {
        'exchange': {
            'balance': 10_000,
            'fee': 0,
            'type': 'futures',
            'futures_leverage': 1,
            'futures_leverage_mode': 'cross',
        },
        'warm_up_candles': 37,
    }
    routes = [{'exchange': 'Worker Exchange'}]

    score, actual_training, actual_testing = fitness.get_fitness(
        user_config,
        routes,
        [],
        [],
        {},
        {},
        {},
        {},
        {},
        10,
        True,
        'research',
        'omega',
    )

    assert score == jh.normalize(2, -0.5, 5)
    assert actual_training == training_metrics
    assert actual_testing == testing_metrics
    assert fitness._formatted_inputs_for_isolated_backtest(user_config, routes)['warm_up_candles'] == 37


def _optimize_until_ray(monkeypatch: pytest.MonkeyPatch, *, initialized: bool) -> list:
    """Run research.optimize with Ray's lifecycle recorded; it stops at its first Ray use."""
    optimize_module = importlib.import_module('jesse.research.optimize')
    events = []

    class StoppedAtRay(Exception):
        pass

    def start(cpu_cores):
        events.append(('start', cpu_cores))
        raise StoppedAtRay

    def reused_runtime_put(value):
        events.append('put')
        raise StoppedAtRay

    def unexpected_raw_init(**kwargs):
        raise AssertionError('Ray must be started through jesse.services.ray_runtime')

    monkeypatch.setattr(optimize_module, 'cpu_count', lambda: 8)
    monkeypatch.setattr(optimize_module, 'initialize_ray', start)
    monkeypatch.setattr(optimize_module.ray, 'init', unexpected_raw_init)
    monkeypatch.setattr(optimize_module.ray, 'is_initialized', lambda: initialized)
    monkeypatch.setattr(optimize_module.ray, 'put', reused_runtime_put)
    monkeypatch.setattr(optimize_module.ray, 'shutdown', lambda: events.append('shutdown'))

    config_input, routes, data_routes, training_candles, testing_candles = _optimization_inputs()
    with pytest.raises(StoppedAtRay):
        research.optimize(
            config=config_input,
            routes=routes,
            data_routes=data_routes,
            training_candles=training_candles,
            training_warmup_candles={},
            testing_candles=testing_candles,
            testing_warmup_candles={},
            cpu_cores=2,
            trials=1,
            progress_bar=False,
        )

    _assert_research_runtime_is_clean()
    return events


def test_optimization_starts_ray_through_the_shared_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _optimize_until_ray(monkeypatch, initialized=False) == [('start', 2)]


def test_optimization_reuses_a_caller_owned_ray_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    # A runtime the caller started is neither restarted nor shut down by the research call.
    assert _optimize_until_ray(monkeypatch, initialized=True) == ['put']


def test_optimization_cleans_parent_state_after_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    optimize_module = importlib.import_module('jesse.research.optimize')

    def fail_after_bootstrap(**_kwargs) -> None:
        config['app']['trading_mode'] = 'optimize'
        router.routes.append(object())
        store.vars['trial'] = 'partial'
        assert jh.is_optimizing() is True
        raise RuntimeError('intentional optimization failure')

    monkeypatch.setattr(optimize_module, '_execute_optimize', fail_after_bootstrap)

    with pytest.raises(RuntimeError, match='intentional optimization failure'):
        research.optimize(
            config={},
            routes=[{'strategy': 'unused'}],
            data_routes=[],
            training_candles={},
            training_warmup_candles={},
            testing_candles={},
            testing_warmup_candles={},
            progress_bar=False,
        )

    _assert_research_runtime_is_clean()
