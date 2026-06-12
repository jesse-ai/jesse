"""
Real-strategy regression tests.

These run full `jesse.research.backtest()` sessions with *real* strategies (adapted
from the maintainer's bot project) over long, fully deterministic synthetic candle
windows, and assert the complete result fingerprint (key metrics rounded to 6
decimals + a sha256 over every closed trade's prices/qty/fees/timestamps) against
values captured from `master` @ EXPECTED_FROM_SHA — i.e. from the code *before* the
perf-backtests optimizations. Any future divergence from these numbers means the
backtest engine's behavior changed, not just its speed.

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

# Expected fingerprints below were captured from master @ this commit
# (pre-optimization reference for the perf-backtests branch):
EXPECTED_FROM_SHA = '0987c304d7f276cfc09c942e53d4c39c9395b8ee'

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


def _ensure_exchange_driver():
    """
    Work around a pre-existing engine quirk (present on master too): the API
    singleton (jesse/services/api.py) builds its sandbox drivers only ONCE, from
    `app.considering_exchanges` at first construction. When a backtest already ran
    in this process against a different exchange name (e.g. the legacy 'Sandbox'
    tests in this suite), orders for a new exchange name are silently dropped
    ("driver not initiated yet") and the backtest reports zero trades. Registering
    our exchange's driver up-front makes these tests independent of suite order.
    """
    from jesse.config import config as jesse_config

    needs_restore = False
    if not jesse_config['app']['considering_exchanges']:
        # allow importing jesse.services.api in a fresh process (its module-level
        # API() construction asserts a non-empty considering_exchanges)
        jesse_config['app']['considering_exchanges'] = (EXCHANGE,)
        needs_restore = True
    try:
        from jesse.exchanges import Sandbox
        from jesse.services.api import api
    finally:
        if needs_restore:
            jesse_config['app']['considering_exchanges'] = []

    if EXCHANGE not in api.drivers:
        api.drivers[EXCHANGE] = Sandbox(EXCHANGE)


def run_scenario(scenario: dict) -> dict:
    """Build deterministic inputs, run research.backtest() and return the fingerprint."""
    import jesse.helpers as jh
    from jesse.research import backtest

    _ensure_exchange_driver()

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
# Expected fingerprints, captured from master @ EXPECTED_FROM_SHA by running
# run_scenario() above with jesse imported from a master checkout (the strategy
# files and candle generation were byte-identical). See docs-perf/REPORT.md.
# ---------------------------------------------------------------------------
SINGLE_ROUTE_EXPECTED = {
    'total': 69,
    'total_winning_trades': 36,
    'total_losing_trades': 33,
    'win_rate': 0.521739,
    'net_profit': -1171.234136,
    'net_profit_percentage': -11.712341,
    'starting_balance': 10000.0,
    'finishing_balance': 8828.765864,
    'fee': 2344.801137,
    'max_drawdown': -31.454717,
    'expectancy_percentage': -0.169744,
    'total_open_trades': 0,
    'open_pl': 0.0,
    'gross_profit': 11184.834972,
    'gross_loss': -12356.069108,
    'longs_count': 32,
    'shorts_count': 37,
    'trades_count': 69,
    'trades_hash': '048ce3b5dc049429',
}

MULTI_ROUTE_EXPECTED = {
    'total': 104,
    'total_winning_trades': 54,
    'total_losing_trades': 50,
    'win_rate': 0.519231,
    'net_profit': 3530.084447,
    'net_profit_percentage': 35.300844,
    'starting_balance': 10000.0,
    'finishing_balance': 13530.084447,
    'fee': 1807.92414,
    'max_drawdown': -11.716148,
    'expectancy_percentage': 0.339431,
    'total_open_trades': 1,
    'open_pl': 0.0,
    'gross_profit': 13892.771438,
    'gross_loss': -10362.686991,
    'longs_count': 64,
    'shorts_count': 40,
    'trades_count': 104,
    'trades_hash': '80e934a1e814f77a',
}


@pytest.mark.slow
def test_real_strategy_single_route():
    """
    ~1 year of 1m candles, BTC-USDT @ 1h, multi-timeframe Alligator/ADX/CMO/SRSI
    strategy (RealStrategyRegression1) with a 4h data route, step simulator.
    Expected values captured from master @ EXPECTED_FROM_SHA (pre-optimization).
    """
    assert run_scenario(SINGLE_ROUTE_SCENARIO) == SINGLE_ROUTE_EXPECTED


@pytest.mark.slow
def test_real_strategy_multi_route():
    """
    ~6 months of 1m candles x 3 routes (Donchian-ATR trend @ 1h, ADX/Williams%R
    @ 15m, Alligator multi-timeframe @ 1h) with two extra 4h data routes, fast
    simulator. Expected values captured from master @ EXPECTED_FROM_SHA
    (pre-optimization).
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
