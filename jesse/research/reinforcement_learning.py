"""
Reinforcement learning for Jesse — train an agent that makes trading decisions
inside a Jesse backtest.

A Jesse backtest is wrapped as a standard Gymnasium environment,
``JesseRLEnvironment``: every ``step()`` hands the agent's action to your
strategy, advances the simulation by one candle, and reads back the new
observation, reward and done-flag through the ``store.rl`` bridge. Training is
done via ``train_rl_agent`` / ``evaluate_rl_agent``,
which run the environment across ``n_envs`` parallel processes for throughput.

Importing this module requires the RL extras — Gymnasium, NumPy and
Stable-Baselines3 (which pulls in PyTorch):
``pip install stable-baselines3 gymnasium torch``.
"""
import hashlib
import inspect
import importlib
import json
import os
import platform
import sys
import time
import traceback
from dataclasses import dataclass

import gymnasium as gym
import numpy as np
import psutil
from stable_baselines3 import DQN, PPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.vec_env import SubprocVecEnv, DummyVecEnv, VecNormalize
from stable_baselines3.common.utils import set_random_seed

import jesse.helpers as jh
from jesse.store import store
from jesse.modes.backtest_mode import (
    run_simulation_iter,
    finalize_simulation
)
from jesse.config import config as jesse_config, set_config, reset_config
from jesse.routes import router
from jesse.repositories import closed_trade_repository
from jesse.services.validators import validate_routes
from jesse.services.candle_service import inject_warmup_candles_to_store
from jesse.services import exchange_service, order_service, position_service
import jesse.services.report as report


def _extract_trading_metrics_from_episode():
    """Extract Jesse's comprehensive trading metrics after an episode completes"""
    
    # Get Jesse's calculated metrics
    portfolio_metrics = report.portfolio_metrics()
    completed_trades = report.trades()
    
    if portfolio_metrics is None:
        return {
            'total_trades': 0,
            'win_rate': 0.0,
            'net_profit_percentage': 0.0,
            'profit_loss': 0.0,
            'sharpe_ratio': 0.0,
            'max_drawdown': 0.0,
            'largest_win': 0.0,
            'largest_loss': 0.0,
            'calmar_ratio': 0.0,
            'avg_win': 0.0,
            'avg_loss': 0.0,
            'starting_balance': 10000.0,  # Default fallback
            'finishing_balance': 10000.0,
            'total_winning_trades': 0,
            'total_losing_trades': 0,
            'longs_percentage': 0.0,
            'shorts_percentage': 0.0,
        }
    
    return {
        'total_trades': portfolio_metrics.get('total', 0),
        'win_rate': portfolio_metrics.get('win_rate', 0.0) * 100,  # Convert to percentage
        'net_profit_percentage': portfolio_metrics.get('net_profit_percentage', 0.0),
        'profit_loss': portfolio_metrics.get('net_profit', 0.0),
        'sharpe_ratio': portfolio_metrics.get('sharpe_ratio', 0.0),
        'max_drawdown': portfolio_metrics.get('max_drawdown', 0.0),
        'largest_win': portfolio_metrics.get('average_win', 0.0),
        'largest_loss': portfolio_metrics.get('average_loss', 0.0),
        'calmar_ratio': portfolio_metrics.get('calmar_ratio', 0.0),
        'avg_win': portfolio_metrics.get('average_win', 0.0),
        'avg_loss': portfolio_metrics.get('average_loss', 0.0),
        'starting_balance': portfolio_metrics.get('starting_balance', 10000.0),
        'finishing_balance': portfolio_metrics.get('finishing_balance', 10000.0),
        'total_winning_trades': portfolio_metrics.get('total_winning_trades', 0),
        'total_losing_trades': portfolio_metrics.get('total_losing_trades', 0),
        'longs_percentage': portfolio_metrics.get('longs_percentage', 0.0),
        'shorts_percentage': portfolio_metrics.get('shorts_percentage', 0.0),
    }


class JesseRLEnvironment(gym.Env):
    """
    Jesse Reinforcement Learning Environment - Optimized for multi-core performance
    """
    
    def __init__(self, config):
        super().__init__()
        
        # Store configuration
        self.backtest_config = config.get('backtest_config')
        self.routes = config.get('routes')
        self.data_routes = config.get('data_routes')
        self.candles = config.get('candles')
        self.warmup_candles = config.get('warmup_candles')
        # Episode length in DECISION bars (trading-timeframe bars). The episode's
        # 1-minute window spans max_steps * trading_tf_minutes candles.
        self.max_steps = config.get('max_steps', 1000)
        # When True, each episode starts at a random offset into the candle array.
        # Across many episodes this samples the entire history rather than always
        # replaying the beginning.
        self.random_episode_start = config.get('random_episode_start', False)
        # warmup_bars > 0 makes random starts SAFE for indicator-based strategies:
        #   1. the random start is snapped to a day boundary (assumes 1-minute input
        #      candles, 1440 per day) so higher-timeframe aggregation isn't cut
        #      mid-candle, and
        #   2. the `warmup_bars` candles immediately BEFORE the start are injected as
        #      warmup, so indicators (EMA/RSI/ATR, anchor timeframes) are warm at the
        #      first traded bar instead of starting cold.
        # 0 -> legacy behaviour (raw random offset, no carved warmup).
        self.warmup_bars = int(config.get('warmup_bars', 0) or 0)

        # Multi-asset training: if a candle pool is provided ({symbol: candle_array}
        # for a single exchange), each episode trades a randomly-chosen symbol from the
        # pool. One policy then learns across many assets, which generalizes far better
        # than memorizing a single symbol. Backward-compatible: absent -> single-asset.
        # RL training does not need trades persisted to the database (they live in
        # memory via report.trades()). Writing every trade — across many parallel
        # env-runner processes — is a per-step cost and a DB-contention hazard.
        closed_trade_repository.set_persistence(False)

        self.candles_pool = config.get('candles_pool')
        self.pool_exchange = config.get('pool_exchange')
        if self.candles_pool:
            self._route_template = dict(self.routes[0])
            _sym0 = next(iter(self.candles_pool))
            self.candles = {f"{self.pool_exchange}-{_sym0}": {
                'exchange': self.pool_exchange, 'symbol': _sym0,
                'candles': self.candles_pool[_sym0]}}

        # Initialize environment state
        self.current_step = 0
        self._sim_generator = None
        
        # Cache strategy instance and spaces (avoid recreating)
        self._cached_strategy = None
        self._action_space = None
        self._observation_space = None
        
        # Pre-format config to avoid repeated formatting
        self._formatted_config = self._format_config(self.backtest_config)
        
        # Get strategy instance to define spaces (minimal initialization for spaces only)
        strategy = self._get_strategy_instance_for_spaces()
        
        # Define action and observation spaces from strategy (cache them)
        self._action_space = strategy.get_action_space()
        self._observation_space = strategy.get_observation_space()
        
        # Don't call reset() here - the trainer calls it when ready
    
    @property
    def action_space(self):
        return self._action_space
    
    @property 
    def observation_space(self):
        return self._observation_space
    
    def _get_strategy_instance_for_spaces(self):
        """Get strategy instance just for defining spaces (minimal setup)"""
        route = self.routes[0]
        strategy = route['strategy']

        # Accept either a strategy name (str) or a strategy class directly (the latter
        # lets callers/tests bypass jesse's sys.path-based strategy-file lookup, exactly
        # like research.backtest does).
        StrategyClass = strategy if isinstance(strategy, type) else jh.get_strategy_class(strategy)
        strategy_instance = StrategyClass()
        
        # Set minimal attributes needed for space definitions
        strategy_instance.exchange = route['exchange']
        strategy_instance.symbol = route['symbol']
        strategy_instance.timeframe = route['timeframe']
        
        return strategy_instance
    
    def _validate_candle_timeframes(self):
        """Validate that candles are 1m candles (same as backtest.py lines 117-126)"""
        for key, value in self.candles.items():
            candle_set = value['candles']
            if candle_set[1][0] - candle_set[0][0] != 60_000:
                raise ValueError(
                    f'Candles passed to the research.backtest() must be 1m candles. '
                    f'\nIf you wish to trade other timeframes, notice that you need to pass it through '
                    f'the timeframe option in your routes. '
                    f'\nThe difference between your candles are {candle_set[1][0] - candle_set[0][0]} milliseconds which more than '
                    f'the accepted 60000 milliseconds.'
                )
    
    def _format_config(self, config):
        """Format config (same as backtest.py _format_config function)"""
        exchange_config = {
            'balance': config['starting_balance'],
            'fee': config['fee'],
            'type': config['type'],
            'name': config['exchange'],
        }
        # futures exchange has different config, so:
        if exchange_config['type'] == 'futures':
            exchange_config['futures_leverage'] = config['futures_leverage']
            exchange_config['futures_leverage_mode'] = config['futures_leverage_mode']

        return {
            'exchanges': {
                config['exchange']: exchange_config
            },
            # All logging OFF during RL: each order/position event otherwise calls the
            # logger which writes a row to the database (jesse.services.logger ->
            # store_log_into_db). At thousands of trades x parallel env-runners that is a
            # large per-step cost and a DB-contention hazard. Training never reads these.
            'logging': {
                'balance_update': False,
                'order_cancellation': False,
                'order_execution': False,
                'order_submission': False,
                'position_closed': False,
                'position_increased': False,
                'position_opened': False,
                'position_reduced': False,
                'shorter_period_candles': False,
                'trading_candles': False
            },
            'warm_up_candles': config['warm_up_candles']
        }
    
    def reset(self, seed=None, options=None):
        """Reset environment to initial state using generator approach - optimized for performance
        
        Args:
            seed: Random seed for environment (optional)
            options: Additional options (optional)
            
        Returns:
            observation: Initial observation
            info: Additional information dictionary
        """
        # Set seed if provided
        if seed is not None:
            np.random.seed(seed)
            
        # Reset episode counters
        self.current_step = 0

        # Multi-asset: pick this episode's symbol from the pool and rebuild
        # self.candles / self.routes for it (the rest of reset() is symbol-agnostic).
        if self.candles_pool:
            _syms = list(self.candles_pool.keys())
            _sym = _syms[int(np.random.randint(len(_syms)))]
            self.candles = {f"{self.pool_exchange}-{_sym}": {
                'exchange': self.pool_exchange, 'symbol': _sym,
                'candles': self.candles_pool[_sym]}}
            self.routes = [dict(self._route_template, symbol=_sym)]

        # Fresh config each episode
        reset_config()
        
        # Initialize router/config like backtest does (BEFORE store.reset())
        jesse_config['app']['trading_mode'] = 'backtest'
        set_config(self._formatted_config)  # Use pre-formatted config
        
        # Initialize routes FIRST (before store.reset())
        router.initiate(self.routes, self.data_routes)
        validate_routes(router)
        
        # NOW reset store (after routes are initialized)
        store.reset()

        # Decide this episode's candle window. `max_steps` is the episode length in
        # DECISION bars (trading-timeframe bars). Input candles are 1-minute, so the
        # window spans `max_steps * trading_tf_minutes` one-minute candles. With
        # random_episode_start the window begins at a random offset so training
        # samples the whole history across episodes rather than only its beginning.
        _primary = next(iter(self.candles.values()))['candles']
        _total_len = len(_primary)
        _tf_1m = jh.timeframe_to_one_minutes(self.routes[0]['timeframe']) if self.routes else 1
        _window = (self.max_steps * _tf_1m) if (self.max_steps and self.max_steps > 0) else _total_len
        _window = min(_window, _total_len)
        if self.random_episode_start and _total_len > _window:
            # Always begin a random episode at a fresh UTC-day boundary so every
            # timeframe (4h, 1d, ...) aggregates from a correct, aligned start —
            # this holds even when warmup_bars == 0. warmup_bars only reserves room
            # before the start to carve warmup from.
            _lo = self.warmup_bars
            _hi = _total_len - _window                       # inclusive max start
            _ts = _primary[:, 0].astype(np.int64)
            _midnights = np.flatnonzero(_ts % 86_400_000 == 0)
            _midnights = _midnights[(_midnights >= _lo) & (_midnights <= _hi)]
            if _midnights.size > 0:
                self._episode_start = int(np.random.choice(_midnights))
            else:
                # No day-aligned start fits (e.g. synthetic candles not on a
                # calendar grid, or a short series) -> fall back to any valid offset.
                self._episode_start = int(np.random.randint(_lo, _hi + 1)) if _hi > _lo else _lo
        else:
            self._episode_start = 0
        self._episode_window = _window
        # candles carved from just before the start, used as this episode's warmup
        self._episode_warmup_start = max(0, self._episode_start - self.warmup_bars)

        # Initialize candle storage (must hold the whole episode window)
        store.candles.init_storage(max(5000, _window + 10))

        # Initialize exchanges/orders/positions state. This mirrors research.backtest's
        # _isolated_backtest(): the simulation generator's _prepare_routes() assigns each
        # position its strategy (store.positions.get_position(...).strategy = ...), which
        # requires the positions state to exist first. Without this the very first step()
        # raises 'NoneType has no attribute strategy' and the episode aborts immediately.
        exchange_service.initialize_exchanges_state()
        order_service.initialize_orders_state()
        position_service.initialize_positions_state()

        # Validate candles only once (cache validation result)
        if not hasattr(self, '_candles_validated'):
            self._validate_candle_timeframes()
            self._candles_validated = True
        
        # OPTIMIZATION: Use shallow copy instead of deep copy for large candle arrays
        # The candle data itself doesn't need to be modified, only the dict structure
        self.trading_candles_dict = {}
        _s, _e = self._episode_start, self._episode_start + self._episode_window
        for key, value in self.candles.items():
            arr = value['candles']
            self.trading_candles_dict[key] = {
                'exchange': value['exchange'],
                'symbol': value['symbol'],
                # slice this episode's window (a view, no copy)
                'candles': arr[_s:_e]
            }
        
        # Same optimization for warmup candles
        self.warmup_candles_dict = {}
        if self.warmup_bars > 0 and self._episode_start > self._episode_warmup_start:
            # Carve warmup from the candles immediately before this episode's window,
            # so indicators are warm at the first traded bar (handles random starts).
            _ws, _we = self._episode_warmup_start, self._episode_start
            for key, value in self.candles.items():
                self.warmup_candles_dict[key] = {
                    'exchange': value['exchange'],
                    'symbol': value['symbol'],
                    'candles': value['candles'][_ws:_we],
                }
        elif self.warmup_candles:
            for key, value in self.warmup_candles.items():
                self.warmup_candles_dict[key] = {
                    'exchange': value['exchange'],
                    'symbol': value['symbol'],
                    'candles': value['candles']  # Reference same array instead of copying
                }
        
        # Inject warmups (optional)
        if self.warmup_candles_dict:
            for c in jesse_config['app']['considering_candles']:
                key = jh.key(c[0], c[1])
                if key in self.warmup_candles_dict:
                    inject_warmup_candles_to_store(
                        self.warmup_candles_dict[key]['candles'], c[0], c[1]
                    )
        
        # Reset RL store
        store.rl.reset()
        
        # Create the simulation generator
        self._sim_generator = run_simulation_iter(
            self.trading_candles_dict,
            hyperparameters=None,
            with_candles_pipeline=True,
            candles_pipeline_class=None,
            candles_pipeline_kwargs=None,
            fast_mode=True  # Use fast mode for RL
        )
        
        # Use cached spaces instead of recreating strategy instance
        store.rl.set_action_space(self._action_space)
        store.rl.set_observation_space(self._observation_space)
        
        # Provide initial observation (zero vector consistent with space)
        obs = np.zeros(self.observation_space.shape, dtype=self.observation_space.dtype)
        store.rl.set_observation(obs)
        
        info = {}
        return obs, info
    
    def step(self, action):
        """Take a step in the environment using generator approach"""
        try:
            # 1) Provide action to strategy via RL store
            store.rl.set_action(action)
            
            # 2) Advance simulation by one chunk using generator
            try:
                next(self._sim_generator)  # advances one candle-chunk; strategy processes action internally
            except StopIteration:
                # No more candles. run_simulation_iter ALREADY called finalize_simulation()
                # when the loop ended (right before the generator stopped) — calling it again
                # here double-records the final daily-balance point and double-terminates
                # strategies, which skews daily-based metrics (Sharpe/Sortino/Calmar) so the
                # RL backtest diverges from a normal research.backtest(). Just read the final
                # state and return; do NOT finalize again.
                obs = store.rl.get_observation()
                if obs is None:
                    obs = np.zeros(self.observation_space.shape, dtype=self.observation_space.dtype)
                # last-step reward still matters (mark-to-market close of the final bar)
                final_reward = store.rl.get_reward() or 0.0
                return obs, float(final_reward), True, True, {}
            
            self.current_step += 1
            
            # 3) Read observation / reward / done from RL store
            obs = store.rl.get_observation()
            if obs is None:
                obs = np.zeros(self.observation_space.shape, dtype=self.observation_space.dtype)
            
            reward = store.rl.get_reward() or 0.0
            terminated = bool(store.rl.is_done())
            truncated = (self.current_step >= self.max_steps)
            
            if terminated or truncated:
                finalize_simulation()
            
            info = {}
            return obs, reward, terminated, truncated, info
        except Exception as e:
            traceback.print_exc()
            # A failure on the very first step of an episode is a structural/setup bug (e.g.
            # uninitialised state, a broken strategy hook) that would otherwise be silently
            # swallowed and turn every episode into a 1-step no-op -- so surface it loudly.
            # Mid-episode failures are treated as a terminal state so one bad episode doesn't
            # kill a long training run.
            if self.current_step == 0:
                raise RuntimeError(f"JesseRLEnvironment.step() failed on the first step: {e}") from e
            print(f"==> ERROR in step at step {self.current_step}: {e}")
            return np.zeros(self.observation_space.shape, dtype=self.observation_space.dtype), 0.0, True, False, {}


# ============================================================================
# Stable-Baselines3-backed trainer
# ----------------------------------------------------------------------------
# Trains across `n_envs` parallel JesseRLEnvironment processes so each env gets
# its own core. That is the actual lever for throughput because RL advances one
# candle at a time through a generator and a single environment pins sampling to
# one core. Benchmarks: 1 env ~2.7k steps/s, 7 envs ~8k steps/s (~3x).
# ============================================================================
def _make_sb3_env(env_config):
    def _f():
        return JesseRLEnvironment(env_config)
    return _f


# ============================================================================
# Result types & persistence
# ============================================================================
# The SB3 model file (model.zip) is opaque: on its own it cannot tell you what
# market, strategy, or library versions produced it. So a saved agent is a
# self-describing *bundle* — the weights plus a manifest plus a snapshot of the
# strategy source — never the .zip alone.
#
# Supported algorithms. DQN is value-based/off-policy (sample-efficient, great
# default for discrete actions); PPO is policy-gradient/on-policy (more stable on
# larger discrete action spaces and the path to continuous actions later). Both
# train through the same JesseRLEnvironment and strategy hooks.
ALGORITHMS = {'DQN': DQN, 'PPO': PPO}


class ObsNormalizer:
    """Standardizes observations with fixed mean/variance (z-score + clip).

    When training normalizes observations, the running statistics it learned must
    be applied identically at evaluation/inference time — otherwise the model sees
    differently-scaled inputs and silently misbehaves. This captures those stats so
    they travel with the model (in the TrainResult and the saved bundle)."""

    def __init__(self, mean, var, clip: float = 10.0, epsilon: float = 1e-8):
        self.mean = np.asarray(mean, dtype=np.float64)
        self.var = np.asarray(var, dtype=np.float64)
        self.clip = float(clip)
        self.epsilon = float(epsilon)

    def normalize(self, obs):
        out = (np.asarray(obs, dtype=np.float64) - self.mean) / np.sqrt(self.var + self.epsilon)
        return np.clip(out, -self.clip, self.clip).astype(np.float32)

    def to_dict(self) -> dict:
        return {'mean': self.mean.tolist(), 'var': self.var.tolist(),
                'clip': self.clip, 'epsilon': self.epsilon}

    @classmethod
    def from_dict(cls, d: dict):
        return cls(d['mean'], d['var'], d.get('clip', 10.0), d.get('epsilon', 1e-8))


@dataclass
class TrainResult:
    """Outcome of `train_rl_agent`. Carries the trained model plus everything
    needed to save a reproducible bundle (config, routes, network arch).

    `normalizer` is the observation normalizer (or None) — it must be passed to
    `evaluate_rl_agent` so inference scales observations the same way training did.
    `best_checkpoint_step` is set when validation checkpoint selection picked an
    earlier checkpoint over the final model."""
    model: object
    algorithm: str
    n_envs: int
    total_timesteps: int
    training_duration: float
    throughput_steps_per_s: float
    network_arch: tuple
    config: dict
    routes: list
    data_routes: list
    normalizer: object = None
    best_checkpoint_step: int = None

    def save(self, name: str = None, *, directory: str = None,
             overwrite: bool = False) -> str:
        """Save this agent as a self-describing bundle and return its path.

        The bundle is a directory containing:
            model.zip      the SB3 weights
            manifest.json  algorithm, config, routes, library versions, and the
                           hash of the strategy source (used to detect drift on load)
            strategy.py    a snapshot of the strategy source, for diffing later

        Args:
            name: bundle name. When omitted, an auto-generated unique name
                (e.g. ``dqn_300000_20260620_141530``) is used, so unnamed saves
                never clobber each other. Pass a name to label an experiment.
            directory: parent folder for the bundle. Defaults to an ``rl_models/``
                folder next to the strategy.
            overwrite: when the target bundle already exists this raises unless
                ``overwrite=True``, in which case the previous model and its
                metrics at that name are replaced (lost).

        Raises on any failure — losing an expensive training run silently is
        worse than a loud error.
        """
        if name is None:
            ts = time.strftime('%Y%m%d_%H%M%S')
            name = f"{self.algorithm.lower()}_{self.total_timesteps}_{ts}"
        parent = directory or _default_models_dir(self.routes)
        path = os.path.join(parent, name)

        if os.path.exists(path):
            if not overwrite:
                raise FileExistsError(
                    f"An RL agent named '{name}' already exists at {path}. "
                    f"Pass overwrite=True to replace it (the previous model and "
                    f"metrics will be lost), or choose a different name.")
            import shutil
            shutil.rmtree(path)
        os.makedirs(path, exist_ok=True)

        self.model.save(os.path.join(path, 'model.zip'))

        source, identity, kind = _capture_strategy_source(self.routes[0]['strategy'])
        if source is not None:
            with open(os.path.join(path, 'strategy.py'), 'w') as f:
                f.write(source)

        manifest = {
            'algorithm': self.algorithm,
            'n_envs': self.n_envs,
            'total_timesteps': self.total_timesteps,
            'training_duration': self.training_duration,
            'throughput_steps_per_s': self.throughput_steps_per_s,
            'network_arch': list(self.network_arch),
            'config': self.config,
            'routes': _serialize_routes(self.routes),
            'data_routes': self.data_routes,
            'strategy': {
                'identity': identity,
                'kind': kind,
                'source_file': 'strategy.py' if source is not None else None,
                'sha256': _sha256(source),
            },
            'versions': _current_versions(),
            'saved_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            # observation normalizer stats (None if training didn't normalize) —
            # required to reproduce the model's inputs at evaluation time.
            'normalizer': self.normalizer.to_dict() if self.normalizer is not None else None,
            'best_checkpoint_step': self.best_checkpoint_step,
        }
        with open(os.path.join(path, 'manifest.json'), 'w') as f:
            json.dump(manifest, f, indent=2, default=str)
        return path


@dataclass
class EvalResult:
    """Outcome of `evaluate_rl_agent`: per-episode rewards plus Jesse's trading
    metrics for the final episode. This is the single source of metrics — read
    `result.metrics` rather than reaching into the global `report` state."""
    episode_rewards: list
    mean_reward: float
    metrics: dict


def _sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest() if text is not None else None


def _current_versions() -> dict:
    import stable_baselines3
    try:
        from jesse.version import __version__ as jesse_version
    except Exception:
        jesse_version = None
    return {
        'jesse': jesse_version,
        'stable_baselines3': stable_baselines3.__version__,
        'python': platform.python_version(),
    }


def _capture_strategy_source(strategy):
    """Return (source_text, identity, kind) for a route's strategy.

    `strategy` is either a strategy name (str) resolved from
    strategies/<name>/__init__.py, or a strategy class object. Grabs the whole
    module file when one exists (captures imports and module-level helpers), and
    falls back to the class source for inline classes that have no file path.
    """
    if isinstance(strategy, str):
        path = f"strategies/{strategy}/__init__.py"
        if os.path.exists(path):
            with open(path) as f:
                return f.read(), strategy, 'name'
        return None, strategy, 'name'

    cls = strategy
    identity = f"{cls.__module__}.{cls.__qualname__}"
    module = sys.modules.get(cls.__module__)
    file_path = getattr(module, '__file__', None)
    if file_path and os.path.exists(file_path):
        with open(file_path) as f:
            return f.read(), identity, 'class_path'
    try:
        return inspect.getsource(cls), identity, 'class_path'
    except (OSError, TypeError):
        return None, identity, 'class_path'


def _serialize_routes(routes: list) -> list:
    """Routes as JSON-safe dicts: a strategy class becomes its import path so the
    manifest stays serializable; a strategy name is kept verbatim."""
    out = []
    for r in routes:
        r = dict(r)
        strat = r['strategy']
        if isinstance(strat, str):
            r['strategy'], r['strategy_kind'] = strat, 'name'
        else:
            r['strategy'] = f"{strat.__module__}.{strat.__qualname__}"
            r['strategy_kind'] = 'class_path'
        out.append(r)
    return out


def _reconstruct_routes(serialized: list) -> list:
    """Inverse of `_serialize_routes`: re-import class-path strategies so the
    returned routes can be passed straight back into `evaluate_rl_agent`. Raises
    a clear error if a class can no longer be imported."""
    out = []
    for r in serialized:
        r = dict(r)
        kind = r.pop('strategy_kind', 'name')
        if kind == 'class_path':
            module_path, _, cls_name = r['strategy'].rpartition('.')
            try:
                r['strategy'] = getattr(importlib.import_module(module_path), cls_name)
            except (ImportError, AttributeError) as e:
                raise ImportError(
                    f"Could not re-import the strategy '{r['strategy']}' recorded in "
                    f"this bundle ({e}). Its file may have moved or been renamed. "
                    f"Re-create the routes manually and pass them to evaluate_rl_agent.")
        out.append(r)
    return out


def _default_models_dir(routes: list) -> str:
    """An `rl_models/` folder next to the (first route's) strategy, falling back
    to the current working directory when the location can't be determined."""
    strat = routes[0]['strategy']
    if isinstance(strat, str):
        base = f"strategies/{strat}"
        if os.path.isdir(base):
            return os.path.join(base, 'rl_models')
    else:
        module = sys.modules.get(strat.__module__)
        file_path = getattr(module, '__file__', None)
        if file_path:
            return os.path.join(os.path.dirname(os.path.abspath(file_path)), 'rl_models')
    return os.path.join(os.getcwd(), 'rl_models')


class _ProgressBarCallback(BaseCallback):
    """Lightweight, dependency-free training progress bar printed to stdout."""

    def __init__(self, total_timesteps: int, width: int = 30):
        super().__init__()
        self._total = max(1, int(total_timesteps))
        self._width = width
        self._t0 = time.time()
        self._last_pct = -1

    def _on_step(self) -> bool:
        pct = min(100, int(self.num_timesteps * 100 / self._total))
        if pct != self._last_pct:
            self._last_pct = pct
            filled = int(self._width * pct / 100)
            bar = '#' * filled + '-' * (self._width - filled)
            elapsed = time.time() - self._t0
            eta = (elapsed / max(pct, 1)) * (100 - pct)
            print(f"\r  [{bar}] {pct:3d}%  {self.num_timesteps:,}/{self._total:,}  "
                  f"elapsed {elapsed:5.0f}s  eta {eta:5.0f}s", end='', flush=True)
            if pct >= 100:
                print()
        return True


class _CheckpointCollector(BaseCallback):
    """Snapshots the policy (and normalization stats) periodically during training
    so the best one can be selected on a validation set afterwards. Keeping copies
    in memory — rather than running the validation backtest mid-training — avoids
    disturbing the live training environments' state."""

    def __init__(self, eval_freq: int):
        super().__init__()
        self.eval_freq = max(1, int(eval_freq))
        self.snapshots = []   # list of (step, policy_state_dict, obs_rms_or_None)
        self._last = 0

    def _grab(self):
        import copy
        state = copy.deepcopy(self.model.policy.state_dict())
        rms = None
        env = self.model.get_env()
        if isinstance(env, VecNormalize) and env.obs_rms is not None:
            rms = (env.obs_rms.mean.copy(), env.obs_rms.var.copy())
        self.snapshots.append((int(self.num_timesteps), state, rms))

    def _on_step(self) -> bool:
        if self.num_timesteps - self._last >= self.eval_freq:
            self._last = self.num_timesteps
            self._grab()
        return True

    def _on_training_end(self) -> None:
        self._grab()   # always include the final model as a candidate


def train_rl_agent(config, routes, data_routes, candles, warmup_candles=None,
                   algorithm: str = 'DQN', total_timesteps: int = 300_000,
                   n_envs: int = None, max_steps: int = 1000,
                   random_episode_start: bool = True, warmup_bars: int = 0,
                   network_arch=(64, 64), progress: bool = False,
                   normalize: bool = False, eval_candles=None,
                   eval_warmup_candles=None, eval_freq: int = 50_000,
                   eval_metric: str = 'net_profit_percentage',
                   seed: int = None) -> TrainResult:
    """Train an RL agent across `n_envs` parallel JesseRLEnvironment processes.

    Returns a `TrainResult` (call `.save()` on it to persist a reusable bundle).

    `algorithm` selects the Stable-Baselines3 algorithm — 'DQN' or 'PPO':
      * DQN  — value-based, off-policy, with a replay buffer that makes it
               sample-efficient; a strong default for discrete actions.
      * PPO  — policy-gradient, on-policy; more stable on larger discrete action
               spaces and the route to continuous actions. Benefits from n_envs>1.

    Episode starts: with random_episode_start, every episode begins at a fresh
    UTC-day boundary so all timeframes (4h, 1d, ...) aggregate from an aligned
    start (always on, even when warmup_bars == 0). `warmup_bars` additionally
    reserves that many 1m candles BEFORE the start and injects them as warmup, so
    indicators and anchor timeframes are warm at the first traded bar instead of
    cold. Assumes 1-minute input candles.

    `normalize`: standardize observations and rewards with running statistics
    during training (often improves stability). The observation stats are returned
    on the TrainResult as `.normalizer` and must be passed to `evaluate_rl_agent`.

    Validation checkpoint selection: pass `eval_candles` (a held-out candle dict)
    to snapshot the model every `eval_freq` steps, score each snapshot on those
    candles by `eval_metric`, and return the BEST one instead of the final model —
    which guards against keeping a model that has started to overfit. Provide
    `eval_warmup_candles` so the validation rollout's indicators are warm.

    `seed`: when set, makes a run reproducible — seeds the main process and the SB3
    algorithm, which propagates per-worker seeds (seed, seed+1, ...) to the env
    processes so each worker's random_episode_start window stream is deterministic.
    Leave as None for nondeterministic training. NOTE: bit-exact reproducibility
    also requires single-threaded math; results are stable run-to-run on the same
    machine/library versions but may differ across machines.

    PORTABILITY: when n_envs > 1 this uses spawned worker processes. On Windows
    and macOS (which use the 'spawn' start method) the calling script MUST be
    guarded by `if __name__ == '__main__':`, otherwise each spawned worker
    re-imports and re-runs the script (recursive process creation). On Linux
    ('fork') the guard is not required but is still good practice. Set n_envs=1
    to run single-process anywhere.
    """
    algorithm = (algorithm or 'DQN').upper()
    if algorithm not in ALGORITHMS:
        raise ValueError(
            f"Unsupported algorithm '{algorithm}'. Choose one of {sorted(ALGORITHMS)}.")
    if n_envs is None:
        n_envs = max(1, (psutil.cpu_count() or 8) - 1)
    env_config = {'backtest_config': config, 'routes': routes, 'data_routes': data_routes,
                  'candles': candles, 'warmup_candles': warmup_candles,
                  'max_steps': max_steps, 'random_episode_start': random_episode_start,
                  'warmup_bars': warmup_bars}
    # Reproducibility: seed the main process here, and pass `seed` to the SB3
    # algorithm below. SB3 propagates it to the (sub)process envs via env.seed(),
    # which lands in JesseRLEnvironment.reset(seed=...) -> np.random.seed, so each
    # worker's random_episode_start window stream is deterministic. Without this,
    # SubprocVecEnv workers self-seed and runs are NOT reproducible across runs.
    if seed is not None:
        set_random_seed(seed)
    VecCls = SubprocVecEnv if n_envs > 1 else DummyVecEnv
    venv = VecCls([_make_sb3_env(env_config) for _ in range(n_envs)])
    _CLIP_OBS = 10.0
    if normalize:
        venv = VecNormalize(venv, norm_obs=True, norm_reward=True, clip_obs=_CLIP_OBS)
    common = dict(policy='MlpPolicy', env=venv, verbose=0, device='cpu', seed=seed,
                  policy_kwargs={'net_arch': list(network_arch)})
    if algorithm == 'DQN':
        model = DQN(learning_rate=1e-4, buffer_size=100_000, learning_starts=2000,
                    batch_size=128, target_update_interval=1000, train_freq=8, **common)
    else:  # PPO
        model = PPO(n_steps=256, batch_size=256, n_epochs=5, **common)
    print(f"RL {algorithm}: training {total_timesteps} steps across {n_envs} env processes...")

    callbacks = []
    if progress:
        callbacks.append(_ProgressBarCallback(total_timesteps))
    collector = _CheckpointCollector(eval_freq) if eval_candles is not None else None
    if collector is not None:
        callbacks.append(collector)

    t0 = time.time()
    model.learn(total_timesteps=total_timesteps, progress_bar=False,
                callback=(callbacks or None))
    dur = time.time() - t0

    def _norm_from_rms(rms):
        return ObsNormalizer(rms[0], rms[1], _CLIP_OBS) if rms is not None else None

    # observation stats from the final training env (the default if no selection)
    final_rms = None
    if normalize and isinstance(venv, VecNormalize) and venv.obs_rms is not None:
        final_rms = (venv.obs_rms.mean.copy(), venv.obs_rms.var.copy())

    best_step = None
    if collector is not None and collector.snapshots:
        # Pick the snapshot that scores best on the held-out validation candles.
        n_eval = next(iter(eval_candles.values()))['candles'].shape[0]
        best = None   # (score, step, state_dict, rms)
        for step, state, rms in collector.snapshots:
            model.policy.load_state_dict(state)
            nrm = _norm_from_rms(rms) if normalize else None
            ev = evaluate_rl_agent(model, config, routes, data_routes, eval_candles,
                                   warmup_candles=eval_warmup_candles,
                                   max_steps=n_eval + 2, normalizer=nrm)
            score = (ev.metrics or {}).get(eval_metric, float('nan'))
            if score != score:   # NaN -> treat as worst
                score = float('-inf')
            if best is None or score > best[0]:
                best = (score, step, state, rms)
        model.policy.load_state_dict(best[2])   # restore the winning checkpoint
        best_step, final_rms = best[1], (best[3] if normalize else None)
        print(f"RL {algorithm}: selected checkpoint at {best_step:,} steps "
              f"(validation {eval_metric}={best[0]:.2f})")

    venv.close()
    return TrainResult(
        model=model, algorithm=algorithm, n_envs=n_envs,
        total_timesteps=total_timesteps, training_duration=dur,
        throughput_steps_per_s=(total_timesteps / dur) if dur else 0.0,
        network_arch=tuple(network_arch), config=config,
        routes=routes, data_routes=data_routes,
        normalizer=_norm_from_rms(final_rms), best_checkpoint_step=best_step,
    )


def evaluate_rl_agent(model, config, routes, data_routes, candles,
                      warmup_candles=None, max_steps: int = None,
                      num_episodes: int = 1, normalizer=None) -> EvalResult:
    """Greedy backtest of a trained RL model over the given candles.

    Returns an `EvalResult` whose `.metrics` is the single source of trading
    metrics for this rollout — no need to read the global `report` afterwards.

    `normalizer`: if the model was trained with observation normalization, pass the
    matching ObsNormalizer (from the TrainResult or a loaded bundle) so inputs are
    scaled exactly as during training.
    """
    env = JesseRLEnvironment({'backtest_config': config, 'routes': routes,
                              'data_routes': data_routes, 'candles': candles,
                              'warmup_candles': warmup_candles,
                              'max_steps': max_steps or 10_000_000,
                              'random_episode_start': False})
    # Discrete actions go to the env as a plain int; continuous (Box) actions must
    # be passed through as the prediction array — casting them to int would truncate
    # the value (e.g. array([0.37]) -> 0) and destroy the policy's output.
    discrete = isinstance(env.action_space, gym.spaces.Discrete)
    rewards = []
    for _ in range(num_episodes):
        obs, _ = env.reset()
        done = trunc = False
        ep = 0.0
        while not (done or trunc):
            pred_obs = normalizer.normalize(obs) if normalizer is not None else obs
            a, _ = model.predict(pred_obs, deterministic=True)
            obs, r, done, trunc, _ = env.step(int(a) if discrete else a)
            ep += r
        rewards.append(ep)
    return EvalResult(
        episode_rewards=rewards,
        mean_reward=float(np.mean(rewards)),
        metrics=_extract_trading_metrics_from_episode(),
    )


def load_rl_agent(path: str, *, ignore_drift: bool = False):
    """Load a saved agent bundle. Returns (model, manifest).

    The manifest's `config` and `routes` are reconstructed (strategy classes
    re-imported) so they can be passed straight back into `evaluate_rl_agent`.

    Safety checks performed on load:
      * strategy source drift — if the current strategy source no longer matches
        the snapshot taken at save time, this WARNS and stops, because the model
        may now be fed observations it was never trained on. Pass
        ``ignore_drift=True`` to proceed anyway (this only suppresses the stop;
        it changes nothing on disk).
      * library versions — a heads-up WARNING if the current jesse / SB3 / Python
        versions differ from those recorded at save time (the .zip format is
        version-sensitive).
      * algorithm — an ERROR if the recorded algorithm is unsupported or the
        weights fail to load into it.
    """
    with open(os.path.join(path, 'manifest.json')) as f:
        manifest = json.load(f)

    # Library-version drift — warn only.
    saved_versions = manifest.get('versions', {})
    for lib, current in _current_versions().items():
        was = saved_versions.get(lib)
        if was is not None and was != current:
            print(f"WARNING: this agent was saved with {lib} {was}, but the current "
                  f"environment has {lib} {current}. Loading may misbehave.")

    # Strategy-source drift — warn, and stop unless ignore_drift.
    strat_meta = manifest.get('strategy', {})
    saved_hash = strat_meta.get('sha256')
    current_source, _, _ = _capture_strategy_source(
        _reconstruct_strategy_identity(strat_meta))
    current_hash = _sha256(current_source)
    if saved_hash is not None and current_hash is not None and saved_hash != current_hash:
        msg = (f"WARNING: the strategy '{strat_meta.get('identity')}' has changed since "
               f"this agent was saved ({manifest.get('saved_at')}). The model may now "
               f"receive observations it was not trained on. Compare against the saved "
               f"snapshot at {os.path.join(path, 'strategy.py')}.")
        if not ignore_drift:
            raise RuntimeError(msg + " Pass ignore_drift=True to load anyway.")
        print(msg + " (ignore_drift=True — loading anyway)")

    algorithm = manifest.get('algorithm')
    if algorithm not in ALGORITHMS:
        raise ValueError(
            f"The bundle manifest records an unsupported algorithm '{algorithm}'. "
            f"Supported algorithms are {sorted(ALGORITHMS)}.")
    try:
        model = ALGORITHMS[algorithm].load(os.path.join(path, 'model.zip'))
    except Exception as e:
        raise RuntimeError(
            f"Failed to load the {algorithm} weights from {path} ({e}). The bundle may "
            f"be corrupt or was saved with an incompatible stable-baselines3 version.")

    manifest['routes'] = _reconstruct_routes(manifest['routes'])
    # rebuild the observation normalizer (if any) so callers can pass it to
    # evaluate_rl_agent and reproduce the model's inputs.
    norm = manifest.get('normalizer')
    manifest['normalizer'] = ObsNormalizer.from_dict(norm) if norm else None
    return model, manifest


def _reconstruct_strategy_identity(strat_meta: dict):
    """Turn a manifest strategy record back into the value `_capture_strategy_source`
    expects: a class object for class-path strategies, or the name string."""
    identity, kind = strat_meta.get('identity'), strat_meta.get('kind')
    if kind == 'class_path' and identity:
        module_path, _, cls_name = identity.rpartition('.')
        try:
            return getattr(importlib.import_module(module_path), cls_name)
        except (ImportError, AttributeError):
            return identity
    return identity
