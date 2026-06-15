import numpy as np
from jesse.strategies import Strategy
import jesse.indicators as ta


class RLParityStrategy(Strategy):
    """
    A fully DETERMINISTIC strategy (fixed EMA-cross rule, ignores any RL action) with
    trivial RL hooks, so the SAME class can be run through both a normal
    research.backtest() and the RL env's run_simulation_iter simulator. Used by
    tests/test_rl_simulator_parity.py to assert the two simulators produce identical
    trades and metrics.
    """

    def get_action_space(self):
        from gymnasium import spaces
        return spaces.Discrete(1)

    def get_observation_space(self):
        from gymnasium import spaces
        return spaces.Box(low=-np.inf, high=np.inf, shape=(1,), dtype=np.float32)

    def get_observation(self):
        return np.zeros(1, dtype=np.float32)

    def calculate_reward(self):
        return 0.0

    def _signal(self):
        if self.candles.shape[0] < 30:
            return 0
        return 1 if ta.ema(self.candles, 10) > ta.ema(self.candles, 30) else -1

    def should_long(self) -> bool:
        return self._signal() == 1

    def should_short(self) -> bool:
        return False

    def should_cancel_entry(self) -> bool:
        return True

    def go_long(self):
        qty = (self.balance * 0.5) / self.price
        self.buy = qty, self.price

    def go_short(self):
        pass

    def update_position(self):
        if self._signal() == -1 and self.is_open:
            self.liquidate()
