"""
RL learning test: the agent must NAIL a trivially-learnable synthetic market.

Trains SB3 on an alternating up/down-trend market where the recent return sign almost
perfectly predicts the next move. Buy-and-hold there is ~0, so any large profit can only
come from the agent learning to ride the regimes. This is the end-to-end proof that the
RL machinery (env -> action -> trade -> reward -> learning) works: it should pass every
time, on every OS/Python the RL extras install on.

Skips unless the RL extras (gymnasium + stable-baselines3 + torch) are installed, so it
never breaks the core suite where those aren't present.
"""
import importlib

import numpy as np
import pytest

pytest.importorskip("gymnasium")
pytest.importorskip("stable_baselines3")
pytest.importorskip("torch")

EXCH, SYM = 'Binance Perpetual Futures', 'BTC-USDT'


def _easy_candles(n=4000, regime=20, step=0.005, noise=0.0001, seed=1):
    """Alternating up/down trends: trivially learnable momentum, ~0 buy & hold."""
    rng = np.random.default_rng(seed)
    ts0 = 1_600_000_000_000; ts0 -= ts0 % 60_000
    rets = np.empty(n)
    for i in range(n):
        d = 1.0 if (i // regime) % 2 == 0 else -1.0
        rets[i] = d * step + noise * rng.standard_normal()
    close = 20_000 * np.exp(np.cumsum(rets))
    open_ = np.empty(n); open_[0] = close[0]; open_[1:] = close[:-1]
    hl = np.abs(rng.normal(0, 0.0001, n)) * close
    high = np.maximum(open_, close) + hl
    low = np.clip(np.minimum(open_, close) - hl, 1e-6, None)
    vol = rng.uniform(10, 100, n)
    ts = ts0 + np.arange(n, dtype=np.int64) * 60_000
    arr = np.column_stack([ts, open_, close, high, low, vol]).astype(np.float64)
    return {f'{EXCH}-{SYM}': {'exchange': EXCH, 'symbol': SYM, 'candles': arr}}


def _strategy_cls():
    return getattr(importlib.import_module('jesse.strategies.RLEasyMomentum'), 'RLEasyMomentum')


def test_rl_agent_learns_easy_market():
    import torch
    from jesse.research.reinforcement_learning import train_rl_agent_sb3, evaluate_rl_agent_sb3
    from jesse.services import report

    torch.manual_seed(0)
    np.random.seed(0)

    config = {'starting_balance': 10_000, 'fee': 0.0, 'type': 'futures', 'futures_leverage': 1,
              'futures_leverage_mode': 'cross', 'exchange': EXCH, 'warm_up_candles': 0}
    routes = [{'exchange': EXCH, 'strategy': _strategy_cls(), 'symbol': SYM, 'timeframe': '1m'}]
    candles = _easy_candles()

    # single process (n_envs=1) -> deterministic, no multiprocessing flakiness in CI.
    res = train_rl_agent_sb3(config, routes, [], candles, algorithm='DQN',
                             total_timesteps=60_000, n_envs=1, max_steps=1000,
                             random_episode_start=True, train_freq=4)
    assert res['model'] is not None

    # greedy backtest over the full market
    evaluate_rl_agent_sb3(res['model'], config, routes, [], candles, max_steps=len(
        candles[f'{EXCH}-{SYM}']['candles']) + 1)
    m = report.portfolio_metrics()

    # buy & hold here is ~0; a learned momentum policy makes a large profit. The threshold
    # is deliberately lenient (optimal is +100s of %) so it never flakes, yet a
    # non-learning/random policy (~0 or negative) cannot pass.
    assert m is not None and m['total'] > 0, "agent never traded"
    assert m['net_profit_percentage'] > 50.0, \
        f"RL agent failed to learn the easy market: net {m['net_profit_percentage']:.1f}% " \
        f"(win {m['win_rate'] * 100:.0f}%, {m['total']} trades)"
