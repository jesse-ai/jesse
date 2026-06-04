import numpy as np

import jesse.helpers as jh
from jesse import research
from jesse.config import reset_config
from jesse.factories import candles_from_close_prices
from jesse.strategies import Strategy
from jesse.candle_pipelines.moving_block_bootstrap import MovingBlockBootstrapCandlesPipeline

# the trading-timeframe candles the strategy actually sees, captured per run
_RECORDED = []


class _CandleRecorderStrategy(Strategy):
    """Records every trading-timeframe candle it is shown. The values come from the candles the
    simulator feeds the strategy — exactly the quantity the fast/full parity bug corrupted."""

    def before(self) -> None:
        _RECORDED.append((
            round(float(self.open), 6), round(float(self.close), 6),
            round(float(self.high), 6), round(float(self.low), 6),
        ))

    def should_long(self) -> bool:
        return False

    def should_short(self) -> bool:
        return False

    def should_cancel_entry(self) -> bool:
        return True

    def go_long(self) -> None:
        pass

    def go_short(self) -> None:
        pass


def _candles_seen(fast_mode: bool) -> list:
    # isolate from whatever ran before in the suite: reset config + clear lru_cached mode helpers
    reset_config()
    for fn in (jh.app_mode, jh.is_live, jh.is_livetrading, jh.is_optimizing, jh.is_paper_trading):
        fn.cache_clear()

    # ~3000 1m candles on a 5m timeframe => the simulator must build 5m candles from the
    # (synthetic) 1m series. A seeded pipeline makes both runs see identical synthetic candles.
    closes = (100 + np.cumsum(np.random.RandomState(0).normal(0, 0.6, 3000))).tolist()
    fake = candles_from_close_prices(closes)
    exchange, symbol, timeframe = 'Fake Exchange', 'FAKE-USDT', '5m'
    config = {
        'starting_balance': 10_000, 'fee': 0.0, 'type': 'futures',
        'futures_leverage': 2, 'futures_leverage_mode': 'cross',
        'exchange': exchange, 'warm_up_candles': 0,
    }
    routes = [{'exchange': exchange, 'strategy': _CandleRecorderStrategy, 'symbol': symbol, 'timeframe': timeframe}]
    candles = {jh.key(exchange, symbol): {'exchange': exchange, 'symbol': symbol, 'candles': fake}}

    _RECORDED.clear()
    research.backtest(
        config, routes, [], candles, fast_mode=fast_mode,
        candles_pipeline_class=MovingBlockBootstrapCandlesPipeline,
        candles_pipeline_kwargs={'batch_size': 500, 'seed': 7},
    )
    return list(_RECORDED)


def test_fast_and_full_simulators_feed_identical_candles_with_pipeline():
    """
    The fast (skip) and full (step) simulators must show the strategy IDENTICAL candles, even
    when a candle pipeline injects synthetic candles. Regression for a bug where the step
    simulator generated higher-timeframe candles from the ORIGINAL candles instead of the
    synthetic ones, so the strategy's view (and indicators) diverged from the fills.
    """
    fast = _candles_seen(True)
    full = _candles_seen(False)

    assert len(fast) > 100  # the strategy actually saw candles (guard against a vacuous pass)
    assert fast == full
