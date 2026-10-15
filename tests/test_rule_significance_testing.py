from copy import deepcopy
import random
import sys

import numpy as np
import pytest

import jesse.helpers as jh
import jesse.indicators as ta
from jesse import research
from jesse.config import config
from jesse.research.rule_significance_testing.common import (
    _annualization_factor,
    _elapsed_annualization_factor,
)
from jesse.research.rule_significance_testing.simulator import run_signal_only_backtest
from jesse.routes import router
from jesse.store import store
from jesse.strategies import Strategy


class NoiseSignal(Strategy):
    """Emit reproducible signals that are independent of the price series."""

    def _signal(self) -> float:
        # Seeding from the bar index keeps the test deterministic while ensuring
        # the strategy cannot infer its signal from candle data.
        return random.Random(10_000 + self.index).random()

    def should_long(self) -> bool:
        return self._signal() < 0.5

    def should_short(self) -> bool:
        return self._signal() >= 0.5

    def go_long(self) -> None:
        # Signal-only backtests inspect should_long/should_short without orders.
        pass

    def go_short(self) -> None:
        pass


class SuperTrendSignal(Strategy):
    """Follow sustained price regimes using Jesse's real SuperTrend indicator."""

    def should_long(self) -> bool:
        trend = ta.supertrend(self.candles, period=10, factor=1).trend
        return self.close > trend

    def should_short(self) -> bool:
        trend = ta.supertrend(self.candles, period=10, factor=1).trend
        return self.close < trend

    def go_long(self) -> None:
        pass

    def go_short(self) -> None:
        pass


def _run_significance_test(strategy: type[Strategy]) -> dict:
    """Run the complete signal backtest and bootstrap against deterministic data."""
    # Twelve-bar directional regimes are long enough for SuperTrend to identify,
    # while the independent noise strategy has no information about their timing.
    log_returns = np.tile(
        np.concatenate((np.full(12, 0.002), np.full(12, -0.002))),
        50,
    )
    prices = 100 * np.exp(np.concatenate(([0.0], np.cumsum(log_returns))))
    candle_array = research.candles_from_close_prices(prices.tolist())
    exchange = 'Fake Exchange'
    symbol = 'BTC-USDT'

    return research.rule_significance_test(
        config={
            'starting_balance': 10_000,
            'fee': 0,
            'type': 'futures',
            'futures_leverage': 1,
            'futures_leverage_mode': 'cross',
            'exchange': exchange,
            'warm_up_candles': 0,
        },
        routes=[{
            'exchange': exchange,
            'strategy': strategy,
            'symbol': symbol,
            'timeframe': '1m',
        }],
        data_routes=[],
        candles={
            jh.key(exchange, symbol): {
                'exchange': exchange,
                'symbol': symbol,
                'candles': candle_array,
            },
        },
        # Keep the real bootstrap large enough to distinguish the two hypotheses
        # reliably without making this focused unit test unnecessarily slow.
        n_simulations=2_000,
        random_seed=42,
        cpu_cores=1,
    )


def _alignment_inputs(strategy: str = 'TestRuleSignificanceAlignment') -> tuple:
    """Build a market whose next return always agrees with an alternating signal."""
    exchange = 'Rule Significance Exchange'
    symbol = 'TEST-USDT'
    observation_count = 120
    edge = 0.002
    signals = np.where(np.arange(observation_count) % 2 == 0, 1.0, -1.0)
    prices = 100 * np.exp(np.concatenate(([0.0], np.cumsum(signals * edge))))
    candle_array = research.candles_from_close_prices(prices.tolist())

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
    candles = {
        jh.key(exchange, symbol): {
            'exchange': exchange,
            'symbol': symbol,
            'candles': candle_array,
        },
    }
    return config_input, routes, candles, edge


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


def _assert_research_runtime_is_clean() -> None:
    assert config['app']['trading_mode'] == ''
    assert router.routes == []
    assert router.data_routes == []
    api_module = sys.modules.get('jesse.services.api')
    if api_module is not None:
        assert api_module.api.drivers == {}
    assert store.vars == {}
    assert store.exchanges.storage == {}
    assert store.orders.storage == {}
    assert jh.is_backtesting() is False
    assert jh.is_optimizing() is False


def test_signal_only_backtest_uses_sparse_clock_events_and_atomic_data_routes():
    start = 1_704_067_200_000
    exchange = 'Sparse Significance Exchange'
    symbol = 'BTC-USDT'
    candles_array = np.array([
        [start + minute * 60_000, 10 + minute, 11 + minute, 12 + minute, 9 + minute, 1 + minute]
        for minute in [0, 1, 12, 14]
    ], dtype=np.float64)
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
        'strategy': 'TestSparseTimestampRoutes',
        'symbol': symbol,
        'timeframe': '5m',
    }]
    data_routes = [{'exchange': exchange, 'symbol': symbol, 'timeframe': '15m'}]
    candles = {
        jh.key(exchange, symbol): {
            'exchange': exchange,
            'symbol': symbol,
            'candles': candles_array,
        },
    }

    timestamps, close_prices, signals = run_signal_only_backtest(
        config_input,
        routes,
        data_routes,
        candles,
    )

    np.testing.assert_array_equal(timestamps, np.array([start + 900_000], dtype=np.int64))
    np.testing.assert_array_equal(close_prices, np.array([25], dtype=np.float64))
    np.testing.assert_array_equal(signals, np.array([0], dtype=np.int8))
    _assert_research_runtime_is_clean()


def test_noise_signal_is_not_statistically_significant():
    result = _run_significance_test(NoiseSignal)

    assert result['n_observations'] == 1_200
    assert result['p_value'] > 0.10
    assert result['annualized_return'] == pytest.approx(
        result['observed_mean'] * 525_600
    )


def test_supertrend_signal_is_statistically_significant():
    result = _run_significance_test(SuperTrendSignal)

    assert result['n_observations'] == 1_200
    assert result['observed_mean'] > 0
    assert result['p_value'] <= 0.05
    assert result['annualized_return'] == pytest.approx(
        result['observed_mean'] * 525_600
    )


def test_successful_significance_run_is_aligned_reproducible_and_isolated():
    config_input, routes, candles, edge = _alignment_inputs()
    expected_config = deepcopy(config_input)
    expected_routes = deepcopy(routes)
    expected_candles = deepcopy(candles)

    single_batch = research.rule_significance_test(
        config_input,
        routes,
        [],
        candles,
        n_simulations=257,
        random_seed=7,
        cpu_cores=1,
    )
    multiple_batches = research.rule_significance_test(
        config_input,
        routes,
        [],
        candles,
        n_simulations=257,
        random_seed=7,
        cpu_cores=3,
    )

    assert single_batch['n_observations'] == 120
    assert single_batch['n_simulations'] == 257
    assert single_batch['observed_mean'] == pytest.approx(edge)
    assert single_batch['annualized_return'] == pytest.approx(edge * 525_600)
    assert single_batch['p_value'] == 0
    assert np.array_equal(
        single_batch['simulated_means'],
        multiple_batches['simulated_means'],
    )
    assert single_batch['p_value'] == multiple_batches['p_value']
    _assert_inputs_unchanged(
        config_input,
        routes,
        candles,
        expected_config,
        expected_routes,
        expected_candles,
    )
    _assert_research_runtime_is_clean()


def test_significance_run_cleans_runtime_after_strategy_failure():
    config_input, routes, candles, _ = _alignment_inputs('TestRuleSignificanceFailure')
    expected_config = deepcopy(config_input)
    expected_routes = deepcopy(routes)
    expected_candles = deepcopy(candles)

    with pytest.raises(RuntimeError, match='intentional significance strategy failure'):
        research.rule_significance_test(
            config_input,
            routes,
            [],
            candles,
            n_simulations=10,
            random_seed=7,
            cpu_cores=2,
        )

    _assert_inputs_unchanged(
        config_input,
        routes,
        candles,
        expected_config,
        expected_routes,
        expected_candles,
    )
    _assert_research_runtime_is_clean()


@pytest.mark.parametrize(
    ('timeframe', 'expected_bars_per_year'),
    [('1m', 525_600), ('1h', 8_760), ('1D', 365)],
)
def test_annualization_uses_route_timeframe(timeframe, expected_bars_per_year):
    assert _annualization_factor(timeframe) == expected_bars_per_year


def test_elapsed_annualization_uses_actual_stock_observation_density():
    year_ms = 365 * 86_400_000

    assert _elapsed_annualization_factor(252 * 390, 0, year_ms) == 252 * 390
