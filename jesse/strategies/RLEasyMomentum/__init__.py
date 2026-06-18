import numpy as np
from gymnasium import spaces
from jesse.strategies import Strategy


class RLEasyMomentum(Strategy):
    """
    Minimal RL strategy used exclusively by tests/test_rl_learns_synthetic.py.

    The test market alternates between an up-trend (+0.5%/bar) and a down-trend
    (-0.5%/bar) every 20 bars. The 3-bar cumulative return sign is nearly a
    perfect label for which regime we are in, so a DQN that learns the mapping
    sign(r3) → action should compound massively. Buy-and-hold on that market
    is ~0%, so a large net profit can only come from the agent actually learning.

    ACTIONS  —  Discrete(3)
    ┌─────┬────────┬─────────────────────────────────────────────────────┐
    │  0  │ flat   │ close any open position, sit in cash                │
    │  1  │ long   │ buy  90% of free balance at the current bar's price │
    │  2  │ short  │ sell 90% of free balance at the current bar's price │
    └─────┴────────┴─────────────────────────────────────────────────────┘

    OBSERVATION  —  Box(shape=(4,), dtype=float32)
    ┌─────┬───────────────────────────────────────────────────────────────┐
    │ [0] │ 1-bar % return, clipped to [-3, 3]                           │
    │     │   e.g. +0.5 → price rose 0.5% last bar                      │
    │ [1] │ 3-bar % return, clipped to [-6, 6]                           │
    │     │   e.g. +1.4 → price up 1.4% over last 3 bars                │
    │ [2] │ sign([1]): +1.0 / 0.0 / -1.0 — the "regime tell"            │
    │     │   on this synthetic market it almost perfectly labels the     │
    │     │   current trend direction                                     │
    │ [3] │ current position: +1.0 = long, 0.0 = flat, -1.0 = short     │
    └─────┴───────────────────────────────────────────────────────────────┘

    REWARD
      % change in total portfolio value per bar:
        (portfolio_value_now - portfolio_value_prev) / portfolio_value_prev * 100
      The test market has zero fees, so the only friction is missed direction.
    """

    _SIZE = 0.9   # fraction of free balance used per entry

    def get_action_space(self):
        # Tells the RL algorithm "the agent picks one of 3 discrete actions".
        # Discrete(3) means the policy outputs a single integer in {0, 1, 2},
        # which self.current_action then exposes to should_long/short/etc.
        return spaces.Discrete(3)

    def get_observation_space(self):
        # Tells the RL algorithm the shape/dtype/bounds of what get_observation
        # returns: a 1-D float32 vector of length 4. low/high = +-inf means we
        # promise nothing about the range (we clip the values ourselves below),
        # so the network sees raw numbers rather than normalized ones.
        return spaces.Box(low=-np.inf, high=np.inf, shape=(4,), dtype=np.float32)

    def get_observation(self) -> np.ndarray:
        # Called once per bar. Returns the 4-number "state" the agent sees before
        # choosing its action. Must match get_observation_space (length 4, float32).
        c = self.candles
        # Not enough history yet (need >=4 closes for r3) -> return a neutral state.
        if c.shape[0] < 6:
            return np.zeros(4, dtype=np.float32)

        # self.candles columns are [ts, open, close, high, low, volume];
        # column index 2 is close. Grab the last 6 closes.
        close = c[-6:, 2]

        # r1: how much price moved over the LAST bar, as a percentage.
        #   e.g. close=[..., 100, 101] -> (101/100 - 1)*100 = +1.0  (up 1%)
        r1 = (close[-1] / close[-2] - 1.0) * 100.0

        # r3: how much price moved over the LAST 3 bars, as a percentage.
        #   close[-4] is 3 bars ago. On this synthetic market the SIGN of r3
        #   almost perfectly reveals the current up/down regime -> "regime tell".
        #   e.g. close[-4]=100, close[-1]=101.5 -> (101.5/100 - 1)*100 = +1.5
        r3 = (close[-1] / close[-4] - 1.0) * 100.0

        # Encode the current open position as a number the network can read:
        #   +1.0 = currently long, -1.0 = currently short, 0.0 = flat.
        pos = 1.0 if self.is_long else (-1.0 if self.is_short else 0.0)

        # Final observation vector. Clipping keeps outliers from dominating the
        # network's input; sign(r3) is the cleanest regime signal (+1/0/-1).
        #   example (mid up-trend, already long):
        #     [ +0.5, +1.5, +1.0, +1.0 ]
        #   example (start of a down-trend, still long -> agent should flip short):
        #     [ -0.5, -1.5, -1.0, +1.0 ]
        return np.array([
            float(np.clip(r1, -3, 3)),   # [0] 1-bar return, capped at +-3%
            float(np.clip(r3, -6, 6)),   # [1] 3-bar return, capped at +-6%
            float(np.sign(r3)),          # [2] regime: +1 up / 0 flat / -1 down
            pos,                         # [3] current position
        ], dtype=np.float32)

    def calculate_reward(self) -> float:
        # Step reward: % change in portfolio value since last bar
        pv = float(self.portfolio_value)
        prev = getattr(self, '_prev_pv', pv)
        self._prev_pv = pv
        return (pv - prev) / prev * 100.0 if prev > 0 else 0.0

    def should_long(self) -> bool:
        return self.current_action == 1

    def should_short(self) -> bool:
        return self.current_action == 2

    def should_cancel_entry(self) -> bool:
        # Always cancel pending entries so the env can re-decide each bar
        return True

    def go_long(self):
        self.buy = (self.balance * self._SIZE) / self.price, self.price

    def go_short(self):
        self.sell = (self.balance * self._SIZE) / self.price, self.price

    def update_position(self):
        # Liquidate when the action conflicts with the current side or goes flat
        wrong_side = (self.current_action == 1 and self.is_short) or \
                     (self.current_action == 2 and self.is_long)
        if self.current_action == 0 or wrong_side:
            self.liquidate()
