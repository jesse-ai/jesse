"""
RL environment behavior tests for two hooks the other RL tests never exercise:

  * is_rl_episode_done() — a strategy can end an episode early, before the candles
    run out or max_steps is hit. We compare an early-stopping strategy against the
    default (run-to-the-end) one and assert it terminates much sooner.
  * warmup_candles — candles injected before the trading window so indicators have
    history; the env must reset and step cleanly when they are provided.

Both drive JesseRLEnvironment directly (no training needed, so it is fast) and run
in a fresh SUBPROCESS for global-state isolation, like the other RL tests here.
"""
import os
import subprocess
import sys


def test_rl_env_behaviors():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run([sys.executable, os.path.abspath(__file__), '--run'],
                          cwd=repo_root, capture_output=True, text=True)
    assert 'ENV_BEHAVIOR_OK' in proc.stdout, (
        "RL env behavior checks failed.\n"
        f"--- stdout ---\n{proc.stdout[-3000:]}\n--- stderr ---\n{proc.stderr[-3000:]}"
    )


# --------------------------------------------------------------------------- #
# Runs in the subprocess (fresh interpreter).
# --------------------------------------------------------------------------- #
def _run():
    import importlib

    import numpy as np

    from jesse.research.reinforcement_learning import JesseRLEnvironment

    EXCH, SYM = 'Binance Perpetual Futures', 'BTC-USDT'
    KEY = f'{EXCH}-{SYM}'
    CONFIG = {'starting_balance': 10_000, 'fee': 0.0, 'type': 'futures', 'futures_leverage': 1,
              'futures_leverage_mode': 'cross', 'exchange': EXCH, 'warm_up_candles': 0}

    def easy_candles(n=300, regime=20, step=0.005, noise=0.0001, seed=1, ts0=None):
        rng = np.random.default_rng(seed)
        if ts0 is None:
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
        return {KEY: {'exchange': EXCH, 'symbol': SYM, 'candles': arr}}, ts0

    base_cls = getattr(importlib.import_module('jesse.strategies.RLEasyMomentum'), 'RLEasyMomentum')

    def rollout_length(strategy_cls, candles, warmup=None, max_steps=5000):
        env = JesseRLEnvironment({'backtest_config': CONFIG,
                                  'routes': [{'exchange': EXCH, 'strategy': strategy_cls,
                                              'symbol': SYM, 'timeframe': '1m'}],
                                  'data_routes': [], 'candles': candles, 'warmup_candles': warmup,
                                  'max_steps': max_steps, 'random_episode_start': False})
        obs, _ = env.reset()
        assert obs.shape == env.observation_space.shape
        steps, done, trunc = 0, False, False
        while not (done or trunc):
            obs, _, done, trunc, _ = env.step(0)
            steps += 1
        return steps, done, trunc

    # --- is_rl_episode_done: early stop vs run-to-the-end ---
    class EarlyStop(base_cls):
        STOP_AT = 30

        def is_rl_episode_done(self) -> bool:
            self._calls = getattr(self, '_calls', 0) + 1
            return self._calls >= self.STOP_AT

    candles, _ = easy_candles(n=300)
    n = candles[KEY]['candles'].shape[0]

    early_steps, early_done, _ = rollout_length(EarlyStop, candles)
    assert early_done is True, "early-stop episode should terminate (not just truncate)"
    assert early_steps < 60, f"early stop ran too long: {early_steps} steps"

    full_steps, _, _ = rollout_length(base_cls, candles)
    assert full_steps > 200, f"default strategy should run to candle end, ran {full_steps}"
    assert full_steps > early_steps * 3, "early stop must end far sooner than a full rollout"

    # --- warmup_candles: env resets and steps cleanly when warmup is provided ---
    warmup, ts0 = easy_candles(n=200, seed=7)
    trading, _ = easy_candles(n=300, seed=1, ts0=ts0 + 200 * 60_000)
    steps, _, _ = rollout_length(base_cls, trading, warmup=warmup)
    assert steps > 0, "rollout with warmup candles produced no steps"

    print("ENV_BEHAVIOR_OK")


if __name__ == '__main__':
    if '--run' in sys.argv:
        _run()
