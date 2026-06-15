"""
Stable-Baselines3 install/train smoke test.

Skips unless the RL extras (gymnasium + stable-baselines3 + torch) are installed, so
it never breaks the core suite. When run in the RL CI matrix (rl-tests.yml), which
installs those extras, a green test on an {OS, Python} cell *proves* SB3 installs and
trains end-to-end on the JesseRLEnvironment there. Uses n_envs=1 (single process) so
the result is purely "does SB3 install + run", independent of multiprocessing.
"""
import numpy as np
import pytest

pytest.importorskip("gymnasium")
pytest.importorskip("stable_baselines3")
pytest.importorskip("torch")

from jesse.research.reinforcement_learning import train_rl_agent_sb3, evaluate_rl_agent_sb3  # noqa: E402

EXCH, SYM = 'Binance', 'BTC-USDT'


def _strategy_cls():
    import importlib
    return getattr(importlib.import_module('jesse.strategies.RLSmokeStrategy'), 'RLSmokeStrategy')


def _candles(n=2000, seed=1):
    rng = np.random.default_rng(seed)
    ts0 = 1_600_000_000_000; ts0 -= ts0 % 60_000
    close = 20_000 * np.exp(np.cumsum(rng.normal(0, 0.001, n)))
    open_ = np.empty(n); open_[0] = close[0]; open_[1:] = close[:-1]
    hl = np.abs(rng.normal(0, 0.0006, n)) * close
    high = np.maximum(open_, close) + hl
    low = np.clip(np.minimum(open_, close) - hl, 1e-6, None)
    vol = rng.uniform(10, 100, n)
    ts = ts0 + np.arange(n) * 60_000
    arr = np.column_stack([ts, open_, close, high, low, vol]).astype(np.float64)
    return {f'{EXCH}-{SYM}': {'exchange': EXCH, 'symbol': SYM, 'candles': arr}}


def test_sb3_trains_and_evaluates():
    config = {'starting_balance': 10_000, 'fee': 0.0, 'type': 'spot',
              'exchange': EXCH, 'warm_up_candles': 0}
    routes = [{'exchange': EXCH, 'strategy': _strategy_cls(), 'symbol': SYM, 'timeframe': '1m'}]
    candles = _candles()

    # single-process (n_envs=1) keeps this purely about "does SB3 install + run"
    res = train_rl_agent_sb3(config, routes, [], candles, algorithm='DQN',
                             total_timesteps=2000, n_envs=1, max_steps=500,
                             random_episode_start=True)
    assert res['model'] is not None
    assert res['total_timesteps'] == 2000
    assert res['training_duration'] > 0

    ev = evaluate_rl_agent_sb3(res['model'], config, routes, [], candles, max_steps=500)
    assert 'mean_reward' in ev
    assert ev['metrics'] is not None
