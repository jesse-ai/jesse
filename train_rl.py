import os
import jesse.factories
import numpy as np
import pandas as pd
import gymnasium as gym
from gymnasium import spaces
import warnings
from typing import Tuple, Dict, Any, Optional
from stable_baselines3 import PPO
from stable_baselines3.common.env_checker import check_env
from stable_baselines3.common.callbacks import EvalCallback, StopTrainingOnRewardThreshold
from stable_baselines3.common.monitor import Monitor
import matplotlib.pyplot as plt

# Suppress warnings for cleaner output
warnings.filterwarnings("ignore")


class TradingEnv(gym.Env):
    """
    Custom Trading Environment for RL training compatible with stable_baselines3.
    """

    def __init__(
        self,
        data: Optional[np.ndarray] = None,
        use_real_data: bool = True,
        symbol: str = "BTCUSDT",
        interval: str = "1m",
        window_size: int = 50,
        initial_balance: float = 10000.0,
        trading_fee: float = 0.001,
        max_steps: int = 1000
    ):
        super(TradingEnv, self).__init__()

        self.symbol = symbol
        self.interval = interval
        self.window_size = window_size
        self.initial_balance = initial_balance
        self.trading_fee = trading_fee
        self.max_steps = max_steps

        # Load or generate data
        if use_real_data and data is None:
            self.data = self._load_sample_data()
        elif data is not None:
            self.data = data
        else:
            self.data = self._generate_sample_data()

        print(f"Loaded data shape: {self.data.shape}")

        # Validate data
        if len(self.data) < self.window_size + 10:
            raise ValueError(
                f"Data too short. Need at least {self.window_size + 10} candles")

        # Action space: 0 = Hold, 1 = Buy, 2 = Sell
        self.action_space = spaces.Discrete(3)

        # Observation space: OHLCV + technical indicators + portfolio state
        # Features per timestep: OHLCV (5) + RSI (1) + MACD (2) + BB (3) = 11
        # Plus portfolio state: balance, position, total_value = 3
        # Total: window_size * 11 + 3
        obs_dim = self.window_size * 11 + 3
        self.observation_space = spaces.Box(
            low=-np.inf,
            high=np.inf,
            shape=(obs_dim,),
            dtype=np.float32
        )

        # Trading state
        self.reset()

    def _load_sample_data(self) -> np.ndarray:
        """Load sample data. In production, integrate with your data fetcher."""
        try:
            # Try to import your data fetcher
            from real_candle import fetch_binance_ohlcv
            data = fetch_binance_ohlcv(self.symbol, self.interval, 1000)
            if data is not None:
                print(f"Loaded real {self.symbol} data")
                return data
        except ImportError:
            print("Could not import data fetcher, using sample data")

        return self._generate_sample_data()

    def _generate_sample_data(self) -> np.ndarray:
        """Generate realistic sample OHLCV data for testing."""
        print("Generating sample data")
        n_candles = 2000

        # Generate price series with trend and noise
        base_price = 50000.0
        trend = np.cumsum(np.random.normal(0, 0.001, n_candles))
        noise = np.random.normal(0, 0.02, n_candles)
        returns = trend + noise

        closes = base_price * np.exp(np.cumsum(returns))

        # Generate OHLCV
        data = []
        for i, close in enumerate(closes):
            # Add some realistic price movement
            volatility = 0.01
            high = close * (1 + abs(np.random.normal(0, volatility)))
            low = close * (1 - abs(np.random.normal(0, volatility)))
            open_price = closes[i-1] if i > 0 else close

            # Ensure OHLC consistency
            high = max(high, open_price, close)
            low = min(low, open_price, close)

            volume = np.random.lognormal(10, 1)  # Log-normal volume
            timestamp = 1640995200000 + i * 60000  # Start from 2022-01-01

            data.append([timestamp, open_price, close, high, low, volume])

        return np.array(data)

    def _calculate_technical_indicators(self, data: np.ndarray) -> Dict[str, np.ndarray]:
        """Calculate technical indicators."""
        closes = data[:, 2]  # Close prices
        highs = data[:, 3]   # High prices
        lows = data[:, 4]    # Low prices

        # RSI
        rsi = self._calculate_rsi(closes, 14)

        # MACD
        macd_line, macd_signal = self._calculate_macd(closes)

        # Bollinger Bands
        bb_upper, bb_middle, bb_lower = self._calculate_bollinger_bands(
            closes, 20)

        return {
            'rsi': rsi,
            'macd_line': macd_line,
            'macd_signal': macd_signal,
            'bb_upper': bb_upper,
            'bb_middle': bb_middle,
            'bb_lower': bb_lower
        }

    def _calculate_rsi(self, prices: np.ndarray, period: int = 14) -> np.ndarray:
        """Calculate RSI indicator."""
        if len(prices) < period + 1:
            return np.full_like(prices, 50.0)  # Return neutral RSI

        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        # Calculate rolling averages properly
        rsi_values = np.full_like(prices, 50.0)

        if len(gains) >= period:
            gain_series = pd.Series(gains)
            loss_series = pd.Series(losses)

            avg_gains = gain_series.rolling(
                window=period, min_periods=period).mean()
            avg_losses = loss_series.rolling(
                window=period, min_periods=period).mean()

            # Fill valid RSI values (skip first value since deltas is one shorter)
            valid_indices = ~(avg_gains.isna() | avg_losses.isna())
            if valid_indices.any():
                rs = avg_gains[valid_indices] / \
                    (avg_losses[valid_indices] + 1e-10)
                calculated_rsi = 100 - (100 / (1 + rs))
                # Map back to original array (offset by 1 due to diff)
                rsi_values[1:][valid_indices] = calculated_rsi.values

        return rsi_values

    def _calculate_macd(self, prices: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Calculate MACD indicator."""
        if len(prices) < 26:
            return np.zeros_like(prices), np.zeros_like(prices)

        try:
            price_series = pd.Series(prices)
            ema_12 = price_series.ewm(span=12, min_periods=12).mean()
            ema_26 = price_series.ewm(span=26, min_periods=26).mean()
            macd_line = ema_12 - ema_26
            macd_signal = macd_line.ewm(span=9, min_periods=9).mean()

            # Fill NaN values with zeros
            macd_line = macd_line.fillna(0).values
            macd_signal = macd_signal.fillna(0).values

            return macd_line, macd_signal
        except Exception:
            return np.zeros_like(prices), np.zeros_like(prices)

    def _calculate_bollinger_bands(self, prices: np.ndarray, period: int = 20) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Calculate Bollinger Bands."""
        if len(prices) < period:
            return prices.copy(), prices.copy(), prices.copy()

        try:
            price_series = pd.Series(prices)
            rolling_mean = price_series.rolling(
                window=period, min_periods=1).mean()
            rolling_std = price_series.rolling(
                window=period, min_periods=1).std()

            # Fill NaN values
            rolling_mean = rolling_mean.fillna(
                method='bfill').fillna(prices[0])
            rolling_std = rolling_std.fillna(
                prices.std() if len(prices) > 1 else 0.01)

            upper = rolling_mean + (rolling_std * 2)
            lower = rolling_mean - (rolling_std * 2)

            return upper.values, rolling_mean.values, lower.values
        except Exception:
            return prices.copy(), prices.copy(), prices.copy()

    def _get_observation(self) -> np.ndarray:
        """Get current observation."""
        # Get current window of data
        start_idx = max(0, self.current_step - self.window_size)
        end_idx = self.current_step

        if end_idx - start_idx < self.window_size:
            # Pad with first available data if at the beginning
            padding = self.window_size - (end_idx - start_idx)
            window_data = np.vstack([
                np.repeat(self.data[[start_idx]], padding, axis=0),
                self.data[start_idx:end_idx]
            ])
        else:
            window_data = self.data[start_idx:end_idx]

        # Calculate technical indicators for the window
        try:
            indicators = self._calculate_technical_indicators(window_data)
        except Exception as e:
            print(f"Warning: Error calculating indicators: {e}")
            # Use fallback values
            indicators = {
                'rsi': np.full(len(window_data), 50.0),
                'macd_line': np.zeros(len(window_data)),
                'macd_signal': np.zeros(len(window_data)),
                'bb_upper': window_data[:, 2] * 1.02,
                'bb_middle': window_data[:, 2],
                'bb_lower': window_data[:, 2] * 0.98
            }

        # Normalize price data (use percentage change)
        normalized_ohlcv = window_data.copy().astype(np.float32)
        if len(normalized_ohlcv) > 1:
            for col in range(1, 5):  # OHLC columns
                price_changes = (
                    window_data[1:, col] / window_data[:-1, col]) - 1
                normalized_ohlcv[1:, col] = price_changes
                normalized_ohlcv[0, col] = 0  # First value

        # Normalize volume (z-score normalization)
        volume_col = normalized_ohlcv[:, 5]
        if volume_col.std() > 0:
            normalized_ohlcv[:, 5] = (
                volume_col - volume_col.mean()) / volume_col.std()
        else:
            normalized_ohlcv[:, 5] = 0

        # Create feature matrix
        features = []
        for i in range(len(normalized_ohlcv)):
            current_price = window_data[i, 2]  # Current close price

            # Price features (already normalized)
            price_features = [
                normalized_ohlcv[i, 1],  # open change
                normalized_ohlcv[i, 3],  # high change
                normalized_ohlcv[i, 4],  # low change
                normalized_ohlcv[i, 2],  # close change
                normalized_ohlcv[i, 5],  # volume (normalized)
            ]

            # Technical indicator features (normalized)
            indicator_features = [
                indicators['rsi'][i] / 100.0,  # RSI (0-1 range)
                # MACD line (tanh normalization)
                np.tanh(indicators['macd_line'][i] / 100.0),
                np.tanh(indicators['macd_signal'][i] / 100.0),  # MACD signal
                (indicators['bb_upper'][i] / current_price) -
                1,  # BB upper distance
                (indicators['bb_middle'][i] / current_price) -
                1,  # BB middle distance
                (indicators['bb_lower'][i] / current_price) -
                1,  # BB lower distance
            ]

            features.extend(price_features + indicator_features)

        # Add portfolio state
        current_price = window_data[-1, 2]  # Current close price
        total_value = self.balance + (self.position * current_price)

        portfolio_features = [
            (self.balance / self.initial_balance) -
            1,  # balance change from initial
            self.position / 10.0,  # position (scaled)
            (total_value / self.initial_balance) - 1  # total value change
        ]

        features.extend(portfolio_features)

        # Ensure we have the right number of features
        expected_features = self.window_size * 11 + 3
        if len(features) != expected_features:
            print(
                f"Warning: Feature count mismatch. Expected {expected_features}, got {len(features)}")
            # Pad or truncate to match expected size
            if len(features) < expected_features:
                features.extend([0.0] * (expected_features - len(features)))
            else:
                features = features[:expected_features]

        # Clip extreme values to prevent overflow
        features = np.clip(features, -10, 10)

        return np.array(features, dtype=np.float32)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.current_step = self.window_size
        self.episode_step = 0
        self.balance = self.initial_balance
        self.position = 0
        self.total_reward = 0
        self.trades = 0

        obs = self._get_observation()
        return obs, {}

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        self.episode_step += 1

        current_price = self.data[self.current_step, 2]  # Close price
        reward = 0.0
        info = {'action': action, 'price': current_price}

        if action == 1 and self.balance > 0:  # Buy
            cost = self.balance * (1 + self.trading_fee)
            self.position += self.balance / current_price
            self.balance = 0
            self.trades += 1
            info['trade'] = 'BUY'

        elif action == 2 and self.position > 0:  # Sell
            proceeds = self.position * current_price * (1 - self.trading_fee)
            self.balance += proceeds
            self.position = 0
            self.trades += 1
            info['trade'] = 'SELL'

        total_value = self.balance + (self.position * current_price)
        reward = (total_value / self.initial_balance) - 1.0

        self.current_step += 1
        done = (
            self.current_step >= len(self.data) - 1 or
            self.episode_step >= self.max_steps or
            total_value <= self.initial_balance * 0.1
        )
        terminated = bool(done)
        truncated = bool(False)

        if done:
            final_return = (total_value / self.initial_balance) - 1.0
            reward += final_return * 10
            info.update({
                'final_balance': self.balance,
                'final_position': self.position,
                'final_value': total_value,
                'total_return': final_return,
                'total_trades': self.trades
            })

        obs = self._get_observation() if not done else np.zeros_like(
            self.observation_space.sample()
        )

        return obs, reward, bool(terminated), bool(truncated), info


def train_trading_agent():
    """Train the trading agent with proper setup."""
    print("Setting up training environment...")

    try:
        # Create environment
        env = TradingEnv(
            use_real_data=True,
            symbol="BTCUSDT",
            interval="1m",
            window_size=30,
            initial_balance=10000.0,
            max_steps=500
        )
        env = Monitor(env, "./logs/")
        # Validate environment
        print("Checking environment...")
        check_env(env, warn=True)
        print("Environment validation passed!")
        # Test a few steps manually
        print("Testing environment...")
        obs, _ = env.reset()
        print(f"Initial observation shape: {obs.shape}")

        for i in range(3):
            action = env.action_space.sample()
            obs, reward, terminated, truncated, info = env.step(action)
            done = terminated or truncated
            print(
                f"Step {i+1}: action={action}, reward={reward:.4f}, done={done}")
            if done:
                obs, _ = env.reset()
                break

        # Create model with optimized hyperparameters
        print("Creating PPO model...")
        model = PPO(
            "MlpPolicy",
            env,
            verbose=1,
            learning_rate=3e-4,
            n_steps=1024,  # Reduced for faster training
            batch_size=64,
            n_epochs=5,  # Reduced for faster training
            gamma=0.99,
            gae_lambda=0.95,
            clip_range=0.2,
            tensorboard_log="./tensorboard_logs/"
        )

        # Setup callbacks
        stop_callback = StopTrainingOnRewardThreshold(
            reward_threshold=0.05,  # Stop when average reward > 5%
            verbose=1
        )

        eval_callback = EvalCallback(
            env,
            best_model_save_path="./best_models/",
            log_path="./eval_logs/",
            eval_freq=2500,  # More frequent evaluation
            deterministic=True,
            render=False,
            callback_on_new_best=stop_callback
        )

        # Create directories
        os.makedirs("./logs/", exist_ok=True)
        os.makedirs("./best_models/", exist_ok=True)
        os.makedirs("./eval_logs/", exist_ok=True)
        os.makedirs("./tensorboard_logs/", exist_ok=True)

        # Train the model
        print("Starting training...")
        model.learn(
            total_timesteps=25000,  # Reduced for faster initial training
            callback=eval_callback,
            progress_bar=True
        )

        # Save final model
        model.save("./ppo_trading_model_final")
        print("Training completed successfully!")

        # Test the trained model
        print("\nTesting trained model...")
        test_model(env, model)

    except Exception as e:
        print(f"Training failed with error: {e}")
        import traceback
        traceback.print_exc()

        # Try to save partial model if it exists
        try:
            if 'model' in locals():
                model.save("./ppo_trading_model_partial")
                print("Saved partial model")
        except:
            pass


def test_model(env, model, episodes=5):
    """Test the trained model."""
    total_rewards = []

    for episode in range(episodes):
        obs, _ = env.reset()
        episode_reward = 0
        done = False
        steps = 0

        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(action)
            done = terminated or truncated
            episode_reward += reward
            steps += 1

            if steps > 500:  # Prevent infinite loops
                break

        total_rewards.append(episode_reward)
        print(f"Episode {episode + 1}: Reward = {episode_reward:.4f}, "
              f"Final Return = {info.get('total_return', 0):.4f}")

    print(f"\nAverage Reward: {np.mean(total_rewards):.4f}")
    print(f"Std Reward: {np.std(total_rewards):.4f}")


if __name__ == "__main__":
    # Run training
    train_trading_agent()
