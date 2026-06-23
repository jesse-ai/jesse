"""
RL continuous-action test: a strategy can expose a continuous (Box) action space,
and the framework must pass the agent's real-valued action through to the strategy
intact — not truncate it to an int.

Three things are checked:
  * A constant continuous action flows through evaluate_rl_agent unchanged. This is
    a regression guard for the int(action) cast that used to live in the eval loop:
    a constant +0.8 "go long, 80% size" action MUST produce trades. If the action
    were cast to int it would become 0 (flat) and nothing would trade.
  * PPO trains end-to-end on a Box action space and evaluates without error.
  * DQN rejects a Box action space (DQN is discrete-only) — documenting why
    continuous actions require PPO.

Runs in a fresh SUBPROCESS for global-state isolation, like the other RL tests.
"""
import os
import subprocess
import sys


def test_rl_continuous_action_space():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run([sys.executable, os.path.abspath(__file__), '--run'],
                          cwd=repo_root, capture_output=True, text=True)
    assert 'CONTINUOUS_OK' in proc.stdout, (
        "RL continuous-action checks failed.\n"
        f"--- stdout ---\n{proc.stdout[-3000:]}\n--- stderr ---\n{proc.stderr[-3000:]}"
    )


# --------------------------------------------------------------------------- #
# Runs in the subprocess (fresh interpreter).
# --------------------------------------------------------------------------- #
def _run():
    import numpy as np

    from jesse.strategies import Strategy
    from jesse.research.reinforcement_learning import train_rl_agent, evaluate_rl_agent

    EXCH, SYM = 'Binance Perpetual Futures', 'BTC-USDT'

    class ContinuousMomentum(Strategy):
        """Box action in [-1, 1]: sign = direction, |value| = position size."""
        def get_action_space(self):
            from gymnasium import spaces
            return spaces.Box(low=-1.0, high=1.0, shape=(1,), dtype=np.float32)

        def get_observation_space(self):
            from gymnasium import spaces
            return spaces.Box(low=-np.inf, high=np.inf, shape=(3,), dtype=np.float32)

        def _target(self) -> float:
            a = self.current_action
            return 0.0 if a is None else float(np.clip(np.asarray(a).reshape(-1)[0], -1, 1))

        def get_observation(self):
            c = self.candles
            if c.shape[0] < 4:
                return np.zeros(3, dtype=np.float32)
            close = c[-4:, 2]
            r1 = (close[-1] / close[-2] - 1.0) * 100.0
            r3 = (close[-1] / close[-4] - 1.0) * 100.0
            pos = 1.0 if self.is_long else (-1.0 if self.is_short else 0.0)
            return np.array([np.clip(r1, -5, 5), np.clip(r3, -10, 10), pos], dtype=np.float32)

        def get_reward(self) -> float:
            pv = float(self.portfolio_value)
            prev = getattr(self, "_prev_pv", pv)
            self._prev_pv = pv
            return (pv - prev) / prev * 100.0 if prev > 0 else 0.0

        def should_long(self) -> bool:
            return self._target() > 0.1

        def should_short(self) -> bool:
            return self._target() < -0.1

        def should_cancel_entry(self) -> bool:
            return True

        def go_long(self):
            self.buy = (self.balance * 0.9 * abs(self._target())) / self.price, self.price

        def go_short(self):
            self.sell = (self.balance * 0.9 * abs(self._target())) / self.price, self.price

        def update_position(self):
            a = self._target()
            if abs(a) <= 0.1 or (a > 0.1 and self.is_short) or (a < -0.1 and self.is_long):
                self.liquidate()

    def candles(n=600, seed=1):
        rng = np.random.default_rng(seed)
        ts0 = 1_600_000_000_000; ts0 -= ts0 % 60_000
        rets = rng.normal(0.0003, 0.001, n)
        close = 20_000 * np.exp(np.cumsum(rets))
        open_ = np.empty(n); open_[0] = close[0]; open_[1:] = close[:-1]
        hl = np.abs(rng.normal(0, 0.0001, n)) * close
        high = np.maximum(open_, close) + hl
        low = np.clip(np.minimum(open_, close) - hl, 1e-6, None)
        vol = rng.uniform(10, 100, n)
        ts = ts0 + np.arange(n, dtype=np.int64) * 60_000
        arr = np.column_stack([ts, open_, close, high, low, vol]).astype(np.float64)
        return {f'{EXCH}-{SYM}': {'exchange': EXCH, 'symbol': SYM, 'candles': arr}}

    config = {'starting_balance': 10_000, 'fee': 0.0, 'type': 'futures', 'futures_leverage': 1,
              'futures_leverage_mode': 'cross', 'exchange': EXCH, 'warm_up_candles': 0}
    routes = [{'exchange': EXCH, 'strategy': ContinuousMomentum, 'symbol': SYM, 'timeframe': '1m'}]
    data = candles()
    n = data[f'{EXCH}-{SYM}']['candles'].shape[0]

    # 1) A constant continuous action must flow through eval intact. A fixed +0.8
    #    ("long, 80% size") has to produce trades; an int() cast would zero it out.
    class ConstModel:
        def predict(self, obs, deterministic=True):
            return np.array([0.8], dtype=np.float32), None

    ev = evaluate_rl_agent(ConstModel(), config, routes, [], data, max_steps=n + 1)
    assert ev.metrics['total_trades'] > 0, \
        "constant +0.8 action produced no trades — the continuous action was lost (int cast?)"

    # 2) PPO trains end-to-end on the Box action space and evaluates without error.
    res = train_rl_agent(config, routes, [], data, algorithm='PPO',
                         total_timesteps=2000, n_envs=1, max_steps=300)
    ev2 = evaluate_rl_agent(res.model, config, routes, [], data, max_steps=n + 1)
    assert isinstance(ev2.metrics, dict) and 'total_trades' in ev2.metrics

    # 3) DQN cannot use a continuous action space.
    raised = False
    try:
        train_rl_agent(config, routes, [], data, algorithm='DQN',
                       total_timesteps=500, n_envs=1, max_steps=300)
    except Exception:
        raised = True
    assert raised, "DQN must reject a Box (continuous) action space"

    print("CONTINUOUS_OK")


if __name__ == '__main__':
    if '--run' in sys.argv:
        _run()
