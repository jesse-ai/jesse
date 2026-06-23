"""
RL multiprocessing test: training with n_envs > 1 must spawn worker processes
(SubprocVecEnv), train, and return a usable model.

This exercises the parallel path the other RL tests skip (they all use n_envs=1 /
DummyVecEnv): the env config — which embeds the strategy class — is shipped to
spawned workers via cloudpickle, each worker rebuilds a JesseRLEnvironment, and
the learner aggregates their rollouts. It is the path the train_rl_agent docstring
warns about needing a __main__ guard, so it deserves direct coverage.

Runs in a fresh SUBPROCESS (which itself then spawns the SB3 workers), mirroring
the other RL tests in this folder.
"""
import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize('algorithm', ['DQN', 'PPO'])
def test_rl_training_with_multiple_envs(algorithm):
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run([sys.executable, os.path.abspath(__file__), '--run', algorithm],
                          cwd=repo_root, capture_output=True, text=True)
    assert 'MULTIPROC_OK' in proc.stdout, (
        f"{algorithm} training with n_envs > 1 failed.\n"
        f"--- stdout ---\n{proc.stdout[-3000:]}\n--- stderr ---\n{proc.stderr[-3000:]}"
    )


# --------------------------------------------------------------------------- #
# Runs in the subprocess (fresh interpreter); this is also the required
# __main__ guard for SubprocVecEnv's spawned workers.
# --------------------------------------------------------------------------- #
def _run(algorithm):
    import importlib

    import numpy as np
    import torch

    from jesse.research.reinforcement_learning import (
        train_rl_agent, evaluate_rl_agent, TrainResult,
    )

    torch.manual_seed(0)
    np.random.seed(0)

    EXCH, SYM = 'Binance Perpetual Futures', 'BTC-USDT'

    def easy_candles(n=1500, regime=20, step=0.005, noise=0.0001, seed=1):
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

    cls = getattr(importlib.import_module('jesse.strategies.RLEasyMomentum'), 'RLEasyMomentum')
    config = {'starting_balance': 10_000, 'fee': 0.0, 'type': 'futures', 'futures_leverage': 1,
              'futures_leverage_mode': 'cross', 'exchange': EXCH, 'warm_up_candles': 0}
    routes = [{'exchange': EXCH, 'strategy': cls, 'symbol': SYM, 'timeframe': '1m'}]
    candles = easy_candles()
    n = candles[f'{EXCH}-{SYM}']['candles'].shape[0]

    res = train_rl_agent(config, routes, [], candles, algorithm=algorithm,
                         total_timesteps=4000, n_envs=2, max_steps=500,
                         random_episode_start=True)
    assert isinstance(res, TrainResult)
    assert res.algorithm == algorithm
    assert res.n_envs == 2, f"expected 2 parallel envs, got {res.n_envs}"

    # The model produced by the parallel path must still be usable for evaluation.
    ev = evaluate_rl_agent(res.model, config, routes, [], candles, max_steps=n + 1)
    assert isinstance(ev.metrics, dict) and 'total_trades' in ev.metrics

    print("MULTIPROC_OK")


if __name__ == '__main__':
    if '--run' in sys.argv:
        _run(sys.argv[-1])
