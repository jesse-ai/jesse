import numpy as np
from jesse.strategies import Strategy

# Tiny RL strategy used only by tests/test_sb3_training.py to confirm Stable-Baselines3
# installs and trains end-to-end on the JesseRLEnvironment for a given OS / Python.


class RLSmokeStrategy(Strategy):
    def get_action_space(self):
        from gymnasium import spaces
        return spaces.Discrete(3)            # 0 flat, 1 long, 2 exit

    def get_observation_space(self):
        from gymnasium import spaces
        return spaces.Box(low=-np.inf, high=np.inf, shape=(4,), dtype=np.float32)

    def get_observation(self) -> np.ndarray:
        c = self.candles
        if c.shape[0] < 6:
            return np.zeros(4, dtype=np.float32)
        close = c[-6:, 2]
        r1 = float(np.clip((close[-1] / close[-2] - 1) * 100, -5, 5))
        r3 = float(np.clip((close[-1] / close[-4] - 1) * 100, -8, 8))
        return np.array([r1, r3, float(self.is_long), 0.0], dtype=np.float32)

    def calculate_reward(self) -> float:
        pv = float(self.portfolio_value)
        prev = getattr(self, '_prev_pv', pv)
        self._prev_pv = pv
        return (pv - prev) / 100.0

    def should_long(self) -> bool:
        return self.current_action == 1

    def should_short(self) -> bool:
        return False

    def should_cancel_entry(self) -> bool:
        return True

    def go_long(self):
        self.buy = (self.balance * 0.5) / self.price, self.price

    def go_short(self):
        pass

    def update_position(self):
        if self.current_action == 2 and self.is_open:
            self.liquidate()
