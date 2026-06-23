"""
RL training-option tests: observation normalization and validation checkpoint
selection.

  * normalize=True returns an ObsNormalizer on the TrainResult, the normalizer
    survives a save/load round-trip, and a reloaded model + normalizer reproduces
    the original evaluation exactly.
  * eval_candles=... snapshots the model during training and returns the
    best-on-validation checkpoint (best_checkpoint_step is set), and the returned
    model evaluates without error.

Runs in a fresh SUBPROCESS for global-state isolation, like the other RL tests.
"""
import os
import subprocess
import sys


def test_rl_training_options():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run([sys.executable, os.path.abspath(__file__), '--run'],
                          cwd=repo_root, capture_output=True, text=True)
    assert 'TRAIN_OPTIONS_OK' in proc.stdout, (
        "RL training-option checks failed.\n"
        f"--- stdout ---\n{proc.stdout[-3000:]}\n--- stderr ---\n{proc.stderr[-3000:]}"
    )


# --------------------------------------------------------------------------- #
# Runs in the subprocess (fresh interpreter).
# --------------------------------------------------------------------------- #
def _run():
    import importlib
    import tempfile
    import shutil

    import numpy as np
    import torch

    from jesse.research.reinforcement_learning import (
        train_rl_agent, evaluate_rl_agent, load_rl_agent, ObsNormalizer,
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
    train_c = easy_candles(seed=1)
    val_c = easy_candles(seed=2)
    n_val = val_c[f'{EXCH}-{SYM}']['candles'].shape[0]

    # 1) Observation normalization: normalizer produced, persisted, reproduced.
    res = train_rl_agent(config, routes, [], train_c, algorithm='PPO',
                         total_timesteps=3000, n_envs=1, max_steps=400, normalize=True)
    assert isinstance(res.normalizer, ObsNormalizer), "normalize=True must yield an ObsNormalizer"

    ev1 = evaluate_rl_agent(res.model, config, routes, [], val_c,
                            max_steps=n_val + 2, normalizer=res.normalizer)
    assert isinstance(ev1.metrics, dict) and 'total_trades' in ev1.metrics

    work = tempfile.mkdtemp()
    try:
        path = res.save('normtest', directory=work)
        model2, manifest = load_rl_agent(path)
        assert isinstance(manifest['normalizer'], ObsNormalizer), "normalizer must survive save/load"
        ev2 = evaluate_rl_agent(model2, manifest['config'], manifest['routes'],
                                manifest['data_routes'], val_c, max_steps=n_val + 2,
                                normalizer=manifest['normalizer'])
        assert abs(ev2.metrics['net_profit_percentage'] - ev1.metrics['net_profit_percentage']) < 1e-6, \
            "reloaded model+normalizer must reproduce the evaluation"
    finally:
        shutil.rmtree(work)

    # 2) Validation checkpoint selection: returns the best-on-val checkpoint.
    res2 = train_rl_agent(config, routes, [], train_c, algorithm='PPO',
                          total_timesteps=4000, n_envs=1, max_steps=400,
                          eval_candles=val_c, eval_freq=1000)
    assert res2.best_checkpoint_step is not None, "checkpoint selection must set best_checkpoint_step"
    ev3 = evaluate_rl_agent(res2.model, config, routes, [], val_c, max_steps=n_val + 2)
    assert isinstance(ev3.metrics, dict) and 'total_trades' in ev3.metrics

    # 3) Both together (normalize + checkpoint selection) must also work.
    res3 = train_rl_agent(config, routes, [], train_c, algorithm='PPO',
                          total_timesteps=4000, n_envs=1, max_steps=400, normalize=True,
                          eval_candles=val_c, eval_freq=1000)
    assert isinstance(res3.normalizer, ObsNormalizer)
    assert res3.best_checkpoint_step is not None

    print("TRAIN_OPTIONS_OK")


if __name__ == '__main__':
    if '--run' in sys.argv:
        _run()
