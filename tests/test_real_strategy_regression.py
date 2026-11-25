"""
Real-strategy regression tests.

These run full `jesse.research.backtest()` sessions with *real* strategies (adapted
from the maintainer's bot project) over long, fully deterministic synthetic candle
windows, and assert the complete result fingerprint (key metrics rounded to 6
decimals + a sha256 over every closed trade's prices/qty/fees/timestamps) against
values captured with completed-only higher-timeframe reads for #656. Any future
unexplained divergence means the engine's behavior changed, not just its speed.
The previous forming-bar fingerprints intentionally differ: excluding unclosed
anchors changes signals and therefore trade counts as well as prices and fees.

A third test (test_fast_mode_equivalence) asserts that the step (fast_mode=False)
and fast (fast_mode=True) simulators produce identical trades on gapless data —
see its docstring for why it deliberately avoids gapped data and max_drawdown.

The candle generator mirrors jesse-bench's: a seeded geometric random walk with a
slow sinusoidal drift (np.random.default_rng), so inputs are bit-identical across
branches and machines.

These tests are intentionally heavy (minutes, not seconds). Deselect them for quick
iterations with: pytest -m "not slow".
"""
import hashlib
import importlib
import importlib.util
import os

import numpy as np
import pytest

# Captured at this revision using an independent boolean-mask candle reader
# (open + timeframe <= decision boundary), rather than the searchsorted reader.
# Scenarios, seeds, candle generation and strategy code are unchanged. The old
# forming-bar baseline originated at 0987c304d7f276cfc09c942e53d4c39c9395b8ee.
CLOSED_CANDLE_REFERENCE_SHA = '74fe8f098d01554b6b44773f964c9e1d7b00cba1'

START_TS = 1609459200000  # 2021-01-01T00:00:00 UTC
EXCHANGE = 'Test Exchange'
_STRATEGIES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'jesse', 'strategies'
)

# ---------------------------------------------------------------------------
# Scenarios. DO NOT EDIT once expected values are captured — any change to the
# candles, config or routes invalidates the recorded fingerprints.
# ---------------------------------------------------------------------------
SINGLE_ROUTE_SCENARIO = dict(
    days=365,           # ~1 year of 1m candles (525,600 trading candles)
    warmup_days=40,     # exactly 240 4h-candles of warmup for the HTF indicators
    routes=[('BTC-USDT', '1h', 'RealStrategyRegression1')],
    data_routes=[('BTC-USDT', '4h')],
    seed_base=7001,
    fast_mode=False,    # exercises the step (per-1m-candle) simulator
)

# Used by test_fast_mode_equivalence below (fast_mode is overridden per run, so the
# value here is irrelevant). Shorter window than SINGLE_ROUTE_SCENARIO so the step
# (per-1m-candle) run stays quick — this scenario is run TWICE.
FAST_MODE_EQUIVALENCE_SCENARIO = dict(
    days=150,           # ~5 months of 1m candles (216,000 trading candles)
    warmup_days=40,     # exactly 240 4h-candles of warmup for the HTF indicators
    routes=[('BTC-USDT', '1h', 'RealStrategyRegression1')],
    data_routes=[('BTC-USDT', '4h')],
    seed_base=9001,
    fast_mode=False,    # placeholder; overridden by the test
)

MULTI_ROUTE_SCENARIO = dict(
    days=180,           # ~6 months x 3 routes (777,600 trading 1m candles total)
    warmup_days=40,
    routes=[
        ('BTC-USDT', '1h', 'RealStrategyRegression2'),
        ('ETH-USDT', '15m', 'RealStrategyRegression3'),
        ('SOL-USDT', '1h', 'RealStrategyRegression1'),
    ],
    data_routes=[('BTC-USDT', '4h'), ('SOL-USDT', '4h')],
    seed_base=8001,
    fast_mode=True,     # exercises the fast (skip) simulator
)


def _gen_candles(seed: int, days: int, warmup_days: int):
    """
    Deterministic synthetic 1m OHLCV: geometric random walk with a slow sinusoidal
    drift (creates trends so the strategies actually trade). Returns
    (warmup_candles, trading_candles), both Nx6 float64 arrays in Jesse order:
    [timestamp, open, close, high, low, volume]. Identical to jesse-bench's
    generator so fingerprints are comparable across branches.
    """
    n = (days + warmup_days) * 1440
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0, 0.0008, n)
    t = np.arange(n)
    drift = 0.00003 * np.sin(t / (1440.0 * 7.0) * 2.0 * np.pi)  # ~2-week cycle
    close = 20000.0 * np.exp(np.cumsum(rets + drift))
    open_ = np.empty(n)
    open_[0] = 20000.0
    open_[1:] = close[:-1]
    wick = np.abs(rng.normal(0.0, 0.0004, n))
    high = np.maximum(open_, close) * (1.0 + wick)
    low = np.minimum(open_, close) * (1.0 - wick)
    vol = rng.uniform(1.0, 100.0, n)
    ts = START_TS + np.arange(n, dtype=np.float64) * 60000.0
    arr = np.column_stack([ts, open_, close, high, low, vol]).astype(np.float64)
    w = warmup_days * 1440
    return arr[:w], arr[w:]


def _load_strategy(name: str):
    """
    Import a test strategy class. Falls back to loading the class straight from this
    repo's jesse/strategies/<name>/__init__.py file, which lets an external capture
    script run the exact same strategy code against a *different* jesse checkout
    (how the master expected-values were recorded).
    """
    try:
        module = importlib.import_module(f'jesse.strategies.{name}')
    except ModuleNotFoundError:
        path = os.path.join(_STRATEGIES_DIR, name, '__init__.py')
        spec = importlib.util.spec_from_file_location(f'_real_strategy_regression_{name}', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return getattr(module, name)


def _fingerprint(result: dict) -> dict:
    """
    Key metrics (floats rounded to 6 decimals) + a sha256 over every closed trade.
    Mirrors jesse-bench's fingerprint logic: if any trade's entry/exit price, qty,
    fee, PNL or timestamps drift by >= 1e-6, the hash changes.
    """
    metric_keys = (
        'total', 'total_winning_trades', 'total_losing_trades', 'win_rate',
        'net_profit', 'net_profit_percentage', 'starting_balance', 'finishing_balance',
        'fee', 'max_drawdown', 'expectancy_percentage', 'total_open_trades',
        'open_pl', 'gross_profit', 'gross_loss', 'longs_count', 'shorts_count',
    )

    def _round(v):
        if isinstance(v, (float, np.floating)):
            return round(float(v), 6)
        if isinstance(v, (int, np.integer)):
            return int(v)
        return v

    metrics = result.get('metrics') or {}
    fp = {k: _round(metrics[k]) for k in metric_keys if k in metrics}
    trades = result.get('trades') or []
    h = hashlib.sha256()
    for tr in trades:
        for k in ('symbol', 'type', 'entry_price', 'exit_price', 'qty', 'fee',
                  'PNL', 'opened_at', 'closed_at', 'holding_period'):
            v = tr.get(k)
            if isinstance(v, (float, np.floating)):
                v = f'{float(v):.6f}'
            h.update(f'{k}={v};'.encode())
        h.update(f'orders={len(tr.get("orders") or [])};'.encode())
    fp['trades_count'] = len(trades)
    fp['trades_hash'] = h.hexdigest()[:16]
    return fp


def run_scenario(scenario: dict) -> dict:
    """Build deterministic inputs, run research.backtest() and return the fingerprint."""
    import jesse.helpers as jh
    from jesse.research import backtest

    config = {
        'starting_balance': 10_000,
        'fee': 0.001,
        'type': 'futures',
        'futures_leverage': 2,
        'futures_leverage_mode': 'cross',
        'exchange': EXCHANGE,
        # realistic indicator slicing (jesse's default); warmup candles themselves
        # are injected explicitly below
        'warm_up_candles': 240,
    }

    routes = [
        {'exchange': EXCHANGE, 'symbol': symbol, 'timeframe': timeframe,
         'strategy': _load_strategy(strategy_name)}
        for symbol, timeframe, strategy_name in scenario['routes']
    ]
    data_routes = [
        {'exchange': EXCHANGE, 'symbol': symbol, 'timeframe': timeframe}
        for symbol, timeframe in scenario['data_routes']
    ]

    candles, warmup_candles = {}, {}
    for i, (symbol, _, _) in enumerate(scenario['routes']):
        w, c = _gen_candles(
            scenario['seed_base'] + i, scenario['days'], scenario['warmup_days']
        )
        key = jh.key(EXCHANGE, symbol)
        candles[key] = {'exchange': EXCHANGE, 'symbol': symbol, 'candles': c}
        warmup_candles[key] = {'exchange': EXCHANGE, 'symbol': symbol, 'candles': w}

    result = backtest(
        config, routes, data_routes, candles,
        warmup_candles=warmup_candles, fast_mode=scenario['fast_mode'],
    )
    return _fingerprint(result)


# ---------------------------------------------------------------------------
# Completed-only fingerprints for #656, captured at CLOSED_CANDLE_REFERENCE_SHA.
# The old forming-bar totals were 69 / 104 trades; closed anchors yield 64 / 100.
# Keep exact metrics and the full closed-trade hash as the regression contract.
# ---------------------------------------------------------------------------
SINGLE_ROUTE_EXPECTED = {
    'total': 64,
    'total_winning_trades': 34,
    'total_losing_trades': 30,
    'win_rate': 0.53125,
    'net_profit': -728.8146,
    'net_profit_percentage': -7.288146,
    'starting_balance': 10000.0,
    'finishing_balance': 9271.1854,
    'fee': 2272.177643,
    'max_drawdown': -28.717608,
    'expectancy_percentage': -0.113877,
    'total_open_trades': 0,
    'open_pl': 0.0,
    'gross_profit': 10991.044733,
    'gross_loss': -11719.859333,
    'longs_count': 31,
    'shorts_count': 33,
    'trades_count': 64,
    'trades_hash': '3979ccf729a8d1b1',
}

MULTI_ROUTE_EXPECTED = {
    'total': 100,
    'total_winning_trades': 51,
    'total_losing_trades': 49,
    'win_rate': 0.51,
    'net_profit': 3512.59439,
    'net_profit_percentage': 35.125944,
    'starting_balance': 10000.0,
    'finishing_balance': 13512.59439,
    'fee': 1683.753958,
    'max_drawdown': -12.254831,
    'expectancy_percentage': 0.351259,
    'total_open_trades': 1,
    'open_pl': 0.0,
    'gross_profit': 13190.648726,
    'gross_loss': -9678.054337,
    'longs_count': 61,
    'shorts_count': 39,
    'trades_count': 100,
    'trades_hash': 'd369048855434720',
}


@pytest.mark.slow
def test_real_strategy_single_route():
    """
    ~1 year of 1m candles, BTC-USDT @ 1h, multi-timeframe Alligator/ADX/CMO/SRSI
    strategy (RealStrategyRegression1) with a 4h data route, step simulator.
    Expected values use the completed-only candle contract described above.
    """
    assert run_scenario(SINGLE_ROUTE_SCENARIO) == SINGLE_ROUTE_EXPECTED


@pytest.mark.slow
def test_real_strategy_multi_route():
    """
    ~6 months of 1m candles x 3 routes (Donchian-ATR trend @ 1h, ADX/Williams%R
    @ 15m, Alligator multi-timeframe @ 1h) with two extra 4h data routes, fast
    simulator. Expected values use the completed-only candle contract described above.
    """
    assert run_scenario(MULTI_ROUTE_SCENARIO) == MULTI_ROUTE_EXPECTED


@pytest.mark.slow
def test_fast_mode_equivalence():
    """
    The same real-strategy backtest run twice — fast_mode=False (step, per-1m-candle
    simulator) then fast_mode=True (fast, skip simulator) — over the same
    deterministic candles must produce IDENTICAL trades: same trades_hash (every
    closed trade's prices/qty/fees/PNL/timestamps), trade counts, net profit,
    finishing balance and total fee. This holds on master too, so it's an invariant
    the perf optimizations must preserve, not a new behavior.

    CLEAN (gapless) DATA ONLY: there is a known, pre-existing divergence between the
    two simulators on GAPPED candle data — they fill gaps ("jumped candles") at
    different granularities, so trades can legitimately differ when gaps exist. That
    bug predates the perf-backtests branch (it reproduces on master) and must not be
    codified here; this test verifies its inputs are strictly contiguous 1m candles
    so it only asserts the equivalence that genuinely holds on both branches.
    """
    scenario = FAST_MODE_EQUIVALENCE_SCENARIO

    # Verify the generator really produces gapless 1m candles (see docstring): every
    # timestamp step is exactly 60,000 ms, including across the warmup/trading seam.
    w, c = _gen_candles(scenario['seed_base'], scenario['days'], scenario['warmup_days'])
    all_ts = np.concatenate([w[:, 0], c[:, 0]])
    assert np.all(np.diff(all_ts) == 60000.0), 'generator produced gapped candles'

    fp_step = run_scenario({**scenario, 'fast_mode': False})
    fp_fast = run_scenario({**scenario, 'fast_mode': True})

    # Sanity: the scenario must actually trade, otherwise equality is vacuous.
    assert fp_step['trades_count'] > 0

    # Intentionally NOT compared: 'max_drawdown' (and any other equity-curve-shaped
    # metric). The step simulator samples equity once per 1m candle while the fast
    # simulator samples it once per skip block, so the drawdown trough is measured
    # at different granularities and legitimately differs between modes even when
    # every trade is identical.
    trade_keys = (
        'trades_hash', 'trades_count', 'total', 'total_winning_trades',
        'total_losing_trades', 'longs_count', 'shorts_count', 'total_open_trades',
        'net_profit', 'finishing_balance', 'fee',
    )
    assert {k: fp_step[k] for k in trade_keys} == {k: fp_fast[k] for k in trade_keys}
