import numpy as np
from jesse.strategies import Strategy

# Momentum RL strategy used by tests/test_rl_learns_synthetic.py on a trivially-learnable
# alternating-trend market: the recent return sign almost perfectly predicts the next
# move, so a correct RL agent should reliably learn to be long in up-regimes and short in
# down-regimes and turn a large profit (buy & hold on that market is ~0).


class RLEasyMomentum(Strategy):
    def get_action_space(self):
        from gymnasium import spaces
        return spaces.Discrete(3)            # 0 flat, 1 long, 2 short

    def get_observation_space(self):
        from gymnasium import spaces
        return spaces.Box(low=-np.inf, high=np.inf, shape=(4,), dtype=np.float32)

    def get_observation(self) -> np.ndarray:
        c = self.candles
        if c.shape[0] < 6:
            return np.zeros(4, dtype=np.float32)
        close = c[-6:, 2]
        r1 = (close[-1] / close[-2] - 1.0) * 100.0
        r3 = (close[-1] / close[-4] - 1.0) * 100.0
        pos = 1.0 if self.is_long else (-1.0 if self.is_short else 0.0)
        return np.array([
            float(np.clip(r1, -3, 3)),
            float(np.clip(r3, -6, 6)),
            float(np.sign(r3)),              # the regime tell
            pos,
        ], dtype=np.float32)

    def calculate_reward(self) -> float:
        pv = float(self.portfolio_value)
        prev = getattr(self, '_prev_pv', pv)
        self._prev_pv = pv
        return (pv - prev) / prev * 100.0 if prev > 0 else 0.0

    def should_long(self) -> bool:
        return self.current_action == 1

    def should_short(self) -> bool:
        return self.current_action == 2

    def should_cancel_entry(self) -> bool:
        return True

    def go_long(self):
        self.buy = (self.balance * 0.9) / self.price, self.price

    def go_short(self):
        self.sell = (self.balance * 0.9) / self.price, self.price

    def update_position(self):
        if self.current_action == 0:
            self.liquidate()
        elif self.current_action == 1 and self.is_short:
            self.liquidate()
        elif self.current_action == 2 and self.is_long:
            self.liquidate()
