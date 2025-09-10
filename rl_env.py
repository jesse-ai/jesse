import gymnasium as gym
from gymnasium import spaces
import numpy as np

# canldes are a way to display the price movement of a crytpocurrency over a specific time period - like 1hr or 1 day
# using fake candles for testing
from jesse.factories.candle_factory import range_candles
# real candle integration
from jesse.factories.real_candle import fetch_binance_ohlcv
from jesse.exchanges.exchange_api import fetch_binance_candles


class TradingEnv(gym.Env):
    metadata = {"render_modes": ["human"], "render_fps": 4}

    """def __init__(self):
        super(TradingEnv, self).__init__()
        self.candles = range_candles(500)
        self.index = 0
        self.balance = 10000
        self.position = 0  # 0: no position, 1: long

        # Observations: [open, close, high, low, volume]
        self.observation_space = spaces.Box(
            low=0, high=np.inf, shape=(5,), dtype=np.float32
        )

        # Actions: 0 = hold, 1 = buy, 2 = sell
        self.action_space = spaces.Discrete(3)

    def reset(self, seed=None, options=None):
        self.index = 0
        self.balance = 10000
        self.position = 0
        return self._get_obs(), {}

    def _get_obs(self):
        candle = self.candles[self.index][1:6]  # skip timestamp
        return candle.astype(np.float32)

    def step(self, action):
        reward = 0
        done = False

        open_price = self.candles[self.index][1]
        close_price = self.candles[self.index][2]

        if action == 1 and self.position == 0:  # buy
            self.position = open_price
        elif action == 2 and self.position != 0:  # sell
            reward = close_price - self.position
            self.balance += reward
            self.position = 0

        self.index += 1
        if self.index >= len(self.candles) - 1:
            done = True

        return self._get_obs(), reward, done, False, {}

    def render(self):
        print(
            f"Index: {self.index}, Balance: {self.balance}, Position: {self.position}")"""  # for fake candles

    def __init__(self, use_real_data=False, symbol="BTCUSDT", interval="1m"):
        super(TradingEnv, self).__init__()

        # Save config
        self.use_real_data = use_real_data
        self.symbol = symbol
        self.interval = interval

        # Load candles
        if self.use_real_data:
            from jesse.factories.real_candle import fetch_binance_ohlcv
            self.candles = fetch_binance_ohlcv(
                self.symbol, self.interval, limit=500)
        else:
            from jesse.factories.candle_factory import range_candles
            self.candles = range_candles(500)

        self.index = 0
        self.balance = 10000
        self.position = 0  # 0: no position, 1: long

        # Observations: [open, close, high, low, volume]
        self.observation_space = spaces.Box(
            low=0, high=np.inf, shape=(5,), dtype=np.float32
        )

        # Actions: 0 = hold, 1 = buy, 2 = sell
        self.action_space = spaces.Discrete(3)

    def _load_data(self):
        if self.use_real_data:
            self.candles = fetch_binance_ohlcv(self.symbol, self.interval)
        else:
            from jesse.factories.candle_factory import range_candles
            self.candles = range_candles(500)

    def reset(self, seed=None, options=None):
        self._load_data()  # refresh candles
        self.index = 0
        self.balance = 10000
        self.position = 0
        return self._get_obs(), {}

    def _get_obs(self):
        # [open, close, high, low, volume]
        candle = self.candles[self.index][1:6]
        return candle.astype(np.float32)

    def step(self, action):
        reward = 0
        done = False
        open_price = self.candles[self.index][1]
        close_price = self.candles[self.index][2]

        if action == 1 and self.position == 0:  # buy
            self.position = open_price
        elif action == 2 and self.position != 0:  # sell
            reward = close_price - self.position
            self.balance += reward
            self.position = 0

        self.index += 1
        if self.index >= len(self.candles) - 1:
            done = True

        return self._get_obs(), reward, done, False, {}

    def render(self):
        print(
            f"Index: {self.index}, Balance: {self.balance}, Position: {self.position}")
