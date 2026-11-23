from copy import deepcopy
import importlib

import optuna
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


class _RecordingSampler(optuna.samplers.RandomSampler):
    """Random sampler that records the value Jesse reports back for every trial."""

    def __init__(self) -> None:
        super().__init__(seed=7)
        self.told = []

    def after_trial(self, study, trial, state, values) -> None:
        self.told.append((trial.params, state, values))
        super().after_trial(study, trial, state, values)


def test_optimization_asks_the_sampler_and_tells_it_each_fitness(monkeypatch: pytest.MonkeyPatch) -> None:
    optimize_module = importlib.import_module('jesse.research.optimize')
    optimize_mode = importlib.import_module('jesse.modes.optimize_mode.Optimize')
    results = {}

    class InlineTrial:
        """Stands in for the Ray remote: scores a trial by its entry_interval so each told value is checkable."""

        def options(self, **_kwargs):
            return self

        def remote(self, *args):
            hp, trial_number = args[4], args[11]
            results[trial_number] = {
                'trial_number': trial_number,
                'score': float(hp['entry_interval']),
                'params': hp,
                'training_metrics': {},
                'testing_metrics': {},
            }
            return trial_number

    monkeypatch.setattr(optimize_mode, 'ray_evaluate_trial', InlineTrial())
    monkeypatch.setattr(optimize_module.ray, 'is_initialized', lambda: True)
    monkeypatch.setattr(optimize_module.ray, 'put', lambda value: value)
    monkeypatch.setattr(optimize_module.ray, 'wait', lambda refs, **_kwargs: (refs[:1], refs[1:]))
    monkeypatch.setattr(optimize_module.ray, 'get', lambda ref: results[ref])

    sampler = _RecordingSampler()
    config_input, routes, data_routes, training_candles, testing_candles = _optimization_inputs()
    result = research.optimize(
        config=config_input,
        routes=routes,
        data_routes=data_routes,
        training_candles=training_candles,
        training_warmup_candles={},
        testing_candles=testing_candles,
        testing_warmup_candles={},
        cpu_cores=2,
        trials=6,
        progress_bar=False,
        sampler=sampler,
    )

    assert result['completed_trials'] == 6
    assert sorted(results) == list(range(6))
    assert {r['params']['entry_interval'] for r in results.values()} <= {4, 5}
    assert len(sampler.told) == 6
    for params, state, values in sampler.told:
        assert state == optuna.trial.TrialState.COMPLETE
        assert values == [float(params['entry_interval'])]
    assert result['best_trials'][0]['fitness'] == max(r['score'] for r in results.values())
    _assert_research_runtime_is_clean()


def test_trial_distributions_match_the_random_sampling_ranges() -> None:
    optimize_module = importlib.import_module('jesse.research.optimize')

    distributions = optimize_module._trial_distributions([
        {'name': 'period', 'type': int, 'min': 10, 'max': 50, 'step': 5},
        {'name': 'length', 'type': 'int', 'min': 2, 'max': 9},
        {'name': 'ratio', 'type': float, 'min': 0.5, 'max': 2.0},
        {'name': 'stop', 'type': 'float', 'min': 0.1, 'max': 0.5, 'step': 0.1},
        {'name': 'source', 'type': 'categorical', 'options': ['close', 'hl2']},
    ])

    assert distributions == {
        'period': optuna.distributions.IntDistribution(10, 50, step=5),
        'length': optuna.distributions.IntDistribution(2, 9),
        'ratio': optuna.distributions.FloatDistribution(0.5, 2.0),
        'stop': optuna.distributions.FloatDistribution(0.1, 0.5, step=0.1),
        'source': optuna.distributions.CategoricalDistribution(['close', 'hl2']),
    }
