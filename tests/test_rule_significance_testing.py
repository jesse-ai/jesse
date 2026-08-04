import random

import numpy as np
import pytest

import jesse.helpers as jh
import jesse.indicators as ta
from jesse import research
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
