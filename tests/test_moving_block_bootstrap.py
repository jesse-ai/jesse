import numpy as np

from jesse.candle_pipelines import MovingBlockBootstrapCandlesPipeline
from jesse.factories import candles_from_close_prices

# the positivity floor the pipeline enforces on rebuilt prices
EPS = 1e-12


def _trending_candles(start: float, end: float, count: int) -> np.ndarray:
    """
    The strongly trending, noisy shape from jesse-ai/jesse#630 (0.60 -> 9.41): late
    bars carry per-bar moves many times larger than early prices, and the noise is
    large relative to the drift so resampled blocks swing both ways. Replaying a
    high-price block at the start price is what dragged an absolute-delta cumsum
    through zero. The compressed per-bar noise (2%) stands in for the issue's
    1000-day, 1m-candle series, where the drift per bar is thousands of times
    smaller than the noise.
    """
    rng = np.random.default_rng(0)
    drift = np.log(end / start) / count
    log_prices = np.log(start) + np.cumsum(drift + rng.normal(0.0, 0.02, count))
    return candles_from_close_prices(np.exp(log_prices).tolist())


def _random_walk_candles(count: int, sigma: float, seed: int = 0) -> np.ndarray:
    """A geometric random walk around 100 with the given per-bar log-return sigma."""
    rng = np.random.default_rng(seed)
    log_returns = rng.normal(0.0, sigma, count)
    closes = 100.0 * np.exp(np.cumsum(log_returns))
    return candles_from_close_prices(closes.tolist())


def _bootstrap(candles: np.ndarray, seed: int = 7) -> np.ndarray:
    """
    Run one synthetic batch through the pipeline the way the framework does:
    last_price is seeded with the first candle's open, then process() rewrites
    a same-shaped output buffer.
    """
    pipeline = MovingBlockBootstrapCandlesPipeline(batch_size=len(candles), seed=seed)
    out = np.zeros((len(candles), 6))
    pipeline.last_price = candles[0, 1]
    assert pipeline.process(candles, out) is True
    return out


def test_trending_series_paths_do_not_collapse_to_the_floor():
    """
    Regression for jesse-ai/jesse#630: resampling absolute-dollar deltas let a block
    from the high-price regime drag the cumulative sum below zero when replayed at
    the start price, pinning the path at the 1e-12 floor and overflowing fills
    downstream. Relative resampling keeps every path positive by construction.
    """
    candles = _trending_candles(0.60, 9.41, 1_000)
    for seed in range(20):
        out = _bootstrap(candles, seed=seed)
        # no path may sit at (or anywhere near) the floor
        assert out[:, 2].min() > 1e-6
        assert not np.isclose(out[:, 2], EPS).any()


def test_synthetic_candles_are_valid_ohlc():
    for candles in (
        _trending_candles(0.60, 9.41, 1_000),
        _random_walk_candles(1_000, 0.01),
    ):
        out = _bootstrap(candles)
        assert (out[:, 1] > 0).all() and (out[:, 2] > 0).all()
        assert (out[:, 3] > 0).all() and (out[:, 4] > 0).all()
        # low <= min(open, close) and high >= max(open, close)
        assert (out[:, 4] <= np.minimum(out[:, 1], out[:, 2]) + 1e-9).all()
        assert (out[:, 3] >= np.maximum(out[:, 1], out[:, 2]) - 1e-9).all()


def test_same_seed_reproduces_the_same_path():
    candles = _random_walk_candles(1_000, 0.01)
    assert np.array_equal(_bootstrap(candles, seed=42), _bootstrap(candles, seed=42))
    assert not np.array_equal(_bootstrap(candles, seed=42), _bootstrap(candles, seed=43))


def test_relative_resampling_preserves_percentage_volatility():
    """
    The scenario distribution must keep the source series' percentage volatility.
    Absolute-dollar resampling inflated it whenever blocks crossed price regimes.
    """
    candles = _random_walk_candles(5_000, 0.01)
    out = _bootstrap(candles)
    original_returns = np.diff(np.log(candles[:, 2]))
    synthetic_returns = np.diff(np.log(out[:, 2]))
    ratio = synthetic_returns.std() / original_returns.std()
    assert 0.8 < ratio < 1.25
