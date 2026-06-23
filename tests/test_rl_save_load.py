"""
RL save/load test: a trained agent must round-trip through disk and reproduce
its evaluation exactly, and the bundle's safety checks must fire.

Trains a tiny agent, saves it as a bundle (model.zip + manifest.json +
strategy.py snapshot), loads it back, and asserts the reloaded model produces
IDENTICAL evaluation metrics — proving the persisted weights and reconstructed
config/routes are faithful. Also checks the overwrite guard and the strategy
source-drift detection (the safeguard against silently feeding a model
observations it was never trained on).

The actual run happens in a fresh SUBPROCESS so it is immune to global-state
pollution from other tests (jesse's research path does not fully isolate every
global), mirroring the other RL tests in this folder.
"""
import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize('algorithm', ['DQN', 'PPO'])
def test_rl_agent_save_load_roundtrip(algorithm):
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run([sys.executable, os.path.abspath(__file__), '--run', algorithm],
                          cwd=repo_root, capture_output=True, text=True)
    assert 'SAVE_LOAD_OK' in proc.stdout, (
        f"{algorithm} save/load round-trip failed.\n"
        f"--- stdout ---\n{proc.stdout[-3000:]}\n--- stderr ---\n{proc.stderr[-3000:]}"
    )


# --------------------------------------------------------------------------- #
# Runs in the subprocess (fresh interpreter).
# --------------------------------------------------------------------------- #
def _run(algorithm):
    import contextlib
    import copy
    import importlib
    import io
    import json
    import shutil
    import tempfile

    import numpy as np
    import torch

    from jesse.research.reinforcement_learning import (
        train_rl_agent, evaluate_rl_agent, load_rl_agent, TrainResult, EvalResult,
    )

    torch.manual_seed(0)
    np.random.seed(0)

    EXCH, SYM = 'Binance Perpetual Futures', 'BTC-USDT'

    def easy_candles(n=2000, regime=20, step=0.005, noise=0.0001, seed=1):
        # Same trivially-learnable alternating-trend market as test_rl_learns_synthetic,
        # just shorter — this test exercises persistence, not learning quality.
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
                         total_timesteps=2000, n_envs=1, max_steps=500,
                         random_episode_start=True)
    assert isinstance(res, TrainResult), "train_rl_agent must return a TrainResult"
    assert res.algorithm == algorithm

    ev = evaluate_rl_agent(res.model, config, routes, [], candles, max_steps=n + 1)
    assert isinstance(ev, EvalResult), "evaluate_rl_agent must return an EvalResult"
    assert isinstance(ev.metrics, dict) and 'total_trades' in ev.metrics

    work = tempfile.mkdtemp()
    try:
        # --- save: bundle is self-describing ---
        path = res.save('roundtrip', directory=work)
        assert sorted(os.listdir(path)) == ['manifest.json', 'model.zip', 'strategy.py']
        man = json.load(open(os.path.join(path, 'manifest.json')))
        assert man['algorithm'] == algorithm
        assert man['strategy']['sha256'] is not None, "strategy source must be hashed"
        assert all(man['versions'].get(k) for k in ('jesse', 'stable_baselines3', 'python'))
        assert man['config'] == config, "config must be stored verbatim for reproducibility"

        # --- auto-name never clobbers; overwrite guard protects named bundles ---
        auto = res.save(directory=work)
        assert os.path.basename(auto).startswith(f'{algorithm.lower()}_2000_')
        try:
            res.save('roundtrip', directory=work)
            raise AssertionError("save to an existing name must raise FileExistsError")
        except FileExistsError:
            pass
        res.save('roundtrip', directory=work, overwrite=True)  # must succeed

        # --- load reproduces the original evaluation exactly ---
        model, manifest = load_rl_agent(path)
        assert isinstance(manifest['routes'][0]['strategy'], type), "route strategy re-imported"
        ev2 = evaluate_rl_agent(model, manifest['config'], manifest['routes'],
                                manifest['data_routes'], candles, max_steps=n + 1)
        assert abs(ev2.metrics['net_profit_percentage'] - ev.metrics['net_profit_percentage']) < 1e-6, \
            "reloaded model diverged on net profit"
        assert ev2.metrics['total_trades'] == ev.metrics['total_trades'], \
            "reloaded model diverged on trade count"

        # --- num_episodes > 1 returns one reward per episode ---
        ev3 = evaluate_rl_agent(model, manifest['config'], manifest['routes'],
                                manifest['data_routes'], candles, max_steps=n + 1,
                                num_episodes=3)
        assert len(ev3.episode_rewards) == 3, "num_episodes must control episode count"

        # Each destructive load check below writes a fresh manifest from this clean base.
        base = json.load(open(os.path.join(path, 'manifest.json')))

        def write_manifest(m):
            json.dump(m, open(os.path.join(path, 'manifest.json'), 'w'))

        # --- library-version mismatch WARNS but still loads ---
        m = copy.deepcopy(base)
        m['versions']['stable_baselines3'] = '0.0.1-fake'
        write_manifest(m)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            load_rl_agent(path)
        out = buf.getvalue()
        assert 'WARNING' in out and 'stable_baselines3' in out, "version drift must warn"

        # --- an unsupported-algorithm bundle is rejected ---
        m = copy.deepcopy(base)
        m['algorithm'] = 'A2C'  # not in the supported set (DQN, PPO)
        write_manifest(m)
        try:
            load_rl_agent(path)
            raise AssertionError("an unsupported-algorithm bundle must raise")
        except ValueError:
            pass

        # --- strategy drift is detected (raises by default, ignore_drift overrides) ---
        m = copy.deepcopy(base)
        m['strategy']['sha256'] = 'deadbeef' * 8
        write_manifest(m)
        try:
            load_rl_agent(path)
            raise AssertionError("strategy drift must raise by default")
        except RuntimeError:
            pass
        load_rl_agent(path, ignore_drift=True)  # must succeed when explicitly allowed

        # --- corrupt weights raise a clear error (last: it breaks the .zip) ---
        write_manifest(base)
        with open(os.path.join(path, 'model.zip'), 'wb') as f:
            f.write(b'not a real model zip')
        try:
            load_rl_agent(path)
            raise AssertionError("corrupt weights must raise")
        except RuntimeError:
            pass
    finally:
        shutil.rmtree(work)

    print("SAVE_LOAD_OK")


if __name__ == '__main__':
    if '--run' in sys.argv:
        _run(sys.argv[-1])
