"""
RL-simulator parity test.

The RL environment (jesse.research.reinforcement_learning.JesseRLEnvironment) drives
the backtest through run_simulation_iter, a different code path from a normal
jesse.research.backtest(). This test asserts the two produce IDENTICAL results
(every trade and every metric, including the daily-balance-based Sharpe) on the same
deterministic strategy + candles — i.e. the RL backtest is accurate, just like the
normal one. It guards against regressions like the double-finalize_simulation() bug
that silently corrupted Sharpe/Sortino/Calmar in the RL path.

The actual comparison runs in a fresh SUBPROCESS so it is immune to global-state
pollution from other tests (jesse's research.backtest does not fully isolate every
global, and `import ray` rewrites sys.path[0]).
"""
import os
import subprocess
import sys


def test_rl_env_matches_normal_backtest():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run([sys.executable, os.path.abspath(__file__), '--run-parity'],
                          cwd=repo_root, capture_output=True, text=True)
    assert 'PARITY_OK' in proc.stdout, (
        "RL-simulator parity check failed.\n"
        f"--- stdout ---\n{proc.stdout[-3000:]}\n--- stderr ---\n{proc.stderr[-3000:]}"
    )


# ---------------------------------------------------------------------------
# Below runs in the subprocess (fresh, clean interpreter): build a deterministic
# strategy + candles, run both simulators, assert identical results, print PARITY_OK.
# ---------------------------------------------------------------------------
def _run_parity():
    import math
    import importlib
    import numpy as np

    from jesse.research import backtest as research_backtest
    from jesse.research.reinforcement_learning import JesseRLEnvironment
    from jesse.services import report

    EXCH, SYM = 'Binance', 'BTC-USDT'
    CONFIG = {'starting_balance': 10_000, 'fee': 0.0006, 'type': 'spot',
              'exchange': EXCH, 'warm_up_candles': 0}

    def routes():
        # pass the strategy CLASS so route validation skips the sys.path-based file lookup
        cls = getattr(importlib.import_module('jesse.strategies.RLParityStrategy'), 'RLParityStrategy')
        return [{'exchange': EXCH, 'strategy': cls, 'symbol': SYM, 'timeframe': '1m'}]

    def make_candles(n=12000, seed=42):
        rng = np.random.default_rng(seed)
        ts0 = 1_600_000_000_000; ts0 -= ts0 % 60_000
        drift = np.sin(np.arange(n) / 600.0) * 0.0010
        close = 20_000 * np.exp(np.cumsum(drift + rng.normal(0, 0.0006, n)))
        open_ = np.empty(n); open_[0] = close[0]; open_[1:] = close[:-1]
        hl = np.abs(rng.normal(0, 0.0005, n)) * close
        high = np.maximum(open_, close) + hl
        low = np.clip(np.minimum(open_, close) - hl, 1e-6, None)
        vol = rng.uniform(10, 100, n)
        ts = ts0 + np.arange(n) * 60_000
        arr = np.column_stack([ts, open_, close, high, low, vol]).astype(np.float64)
        return {f'{EXCH}-{SYM}': {'exchange': EXCH, 'symbol': SYM, 'candles': arr}}

    candles = make_candles()
    normal = research_backtest(CONFIG, routes(), [], candles, fast_mode=True,
                               generate_charts=False)['metrics']

    n = next(iter(candles.values()))['candles'].shape[0]
    env = JesseRLEnvironment({'backtest_config': CONFIG, 'routes': routes(), 'data_routes': [],
                              'candles': candles, 'warmup_candles': None,
                              'max_steps': n + 5, 'random_episode_start': False})
    obs, _ = env.reset()
    done = trunc = False
    while not (done or trunc):
        obs, rew, done, trunc, _ = env.step(0)  # action ignored by the deterministic strategy
    rl = report.portfolio_metrics()

    assert normal is not None and rl is not None, "one path returned no metrics"
    assert normal['total'] > 0, "no trades — test is vacuous"

    for key in ['total', 'net_profit_percentage', 'win_rate', 'finishing_balance',
                'total_winning_trades', 'total_losing_trades', 'max_drawdown',
                'sharpe_ratio', 'sortino_ratio', 'calmar_ratio']:
        a, b = normal.get(key), rl.get(key)
        if a is None and b is None:
            continue
        assert a is not None and b is not None, f"{key}: one side missing ({a} vs {b})"
        fa, fb = float(a), float(b)
        if math.isnan(fa) and math.isnan(fb):
            continue
        if math.isinf(fa) and math.isinf(fb) and (fa > 0) == (fb > 0):
            continue
        assert abs(fa - fb) < 1e-6, f"RL simulator diverges on {key}: {a} vs {b}"

    print(f"trades={normal['total']} net={normal['net_profit_percentage']:.4f} "
          f"sharpe={normal['sharpe_ratio']:.4f}")
    print("PARITY_OK")


if __name__ == '__main__':
    if '--run-parity' in sys.argv:
        _run_parity()
