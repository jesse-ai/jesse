import ray
from ray import tune
from ray.rllib.env.env_context import EnvContext
from ray.rllib.algorithms.dqn import DQN, DQNConfig
import gymnasium as gym
from gymnasium import spaces
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
import copy
import psutil
import time
import threading

from jesse.research.backtest import backtest as _backtest
import jesse.helpers as jh
from jesse.store import store
from jesse.modes.backtest_mode import (
    run_simulation_iter,
    finalize_simulation
)
from jesse.config import config as jesse_config, set_config, reset_config
from jesse.routes import router
from jesse.services.validators import validate_routes
from jesse.services.candle import inject_warmup_candles_to_store
import jesse.services.metrics as stats
import jesse.services.report as report


class PerformanceMonitor:
    """Monitor CPU and memory usage during RL training"""
    
    def __init__(self, num_workers: int):
        self.num_workers = num_workers
        self.monitoring = False
        self.cpu_usage_history = []
        self.memory_usage_history = []
        self.cpu_count = psutil.cpu_count()
        self._monitor_thread = None
    
    def start_monitoring(self):
        """Start monitoring in a separate thread"""
        self.monitoring = True
        self.cpu_usage_history = []
        self.memory_usage_history = []
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        jh.debug(f"Performance monitoring started. System has {self.cpu_count} CPUs, using {self.num_workers} workers")
    
    def stop_monitoring(self):
        """Stop monitoring and return summary"""
        self.monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=1)
        
        if self.cpu_usage_history:
            avg_cpu = np.mean(self.cpu_usage_history)
            max_cpu = np.max(self.cpu_usage_history)
            avg_memory = np.mean(self.memory_usage_history)
            
            expected_cpu_usage = (self.num_workers / self.cpu_count) * 100
            efficiency = avg_cpu / expected_cpu_usage if expected_cpu_usage > 0 else 0
            
            return {
                'avg_cpu_percent': avg_cpu,
                'max_cpu_percent': max_cpu,
                'avg_memory_percent': avg_memory,
                'expected_cpu_percent': expected_cpu_usage,
                'cpu_efficiency': efficiency,
                'total_cpus': self.cpu_count,
                'workers_used': self.num_workers
            }
        return {}
    
    def _monitor_loop(self):
        """Monitor CPU and memory usage in a loop"""
        while self.monitoring:
            try:
                cpu_percent = psutil.cpu_percent(interval=1)
                memory_percent = psutil.virtual_memory().percent
                
                self.cpu_usage_history.append(cpu_percent)
                self.memory_usage_history.append(memory_percent)
            except Exception:
                pass  # Continue silently


def _fmt(x, decimals=2, sci=False):
    """Format number for display"""
    if x is None:
        return "NA"
    try:
        x = float(x)
        return f"{x:.2e}" if sci else f"{x:.{decimals}f}"
    except Exception:
        return str(x)


def _get_any(d, keys):
    """Get first available key from dict"""
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return None


def _get_nested(d, parent, key):
    """Get nested value from dict"""
    p = d.get(parent)
    if isinstance(p, dict):
        return p.get(key)
    return None


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


def _enhanced_episode_summary(trading_metrics: dict, episode_num: int) -> str:
    """Create detailed episode summary with trading metrics"""
    if trading_metrics['total_trades'] == 0:
        return f"Episode {episode_num}: No trades executed"
    
    profit_loss = trading_metrics['net_profit_percentage']
    profit_symbol = "+" if profit_loss >= 0 else ""
    
    return (
        f"Episode {episode_num} Complete:\n"
        f"    Portfolio:     ${trading_metrics['starting_balance']:,.0f} → "
        f"${trading_metrics['finishing_balance']:,.0f} ({profit_symbol}{profit_loss:.2f}%)\n"
        f"    Trading:       {trading_metrics['total_trades']} trades, "
        f"{trading_metrics['total_winning_trades']} wins, "
        f"{trading_metrics['total_losing_trades']} losses "
        f"(Win Rate: {trading_metrics['win_rate']:.1f}%)\n"
        f"    Performance:   Sharpe: {trading_metrics['sharpe_ratio']:.2f}, "
        f"Max DD: {trading_metrics['max_drawdown']:.1f}%, "
        f"Calmar: {trading_metrics['calmar_ratio']:.2f}\n"
        f"    Positions:     Longs: {trading_metrics['longs_percentage']:.1f}%, "
        f"Shorts: {trading_metrics['shorts_percentage']:.1f}%"
    )


def _summarize_training_result(result: dict, iteration: int) -> dict:
    """Extract key metrics from training result for readable summary"""
    # reward/return
    ret_mean = _get_any(result, ['episode_reward_mean', 'episode_return_mean', 'env_runners/episode_return_mean'])
    if ret_mean is None:
        ret_mean = _get_nested(result, 'sampler_results', 'episode_reward_mean') or \
                   _get_nested(result, 'sampler_results', 'episode_return_mean') or \
                   _get_nested(result, 'env_runners', 'episode_return_mean')
    ret_min = _get_any(result, ['episode_reward_min', 'episode_return_min']) or \
              _get_nested(result, 'env_runners', 'episode_return_min')
    ret_max = _get_any(result, ['episode_reward_max', 'episode_return_max']) or \
              _get_nested(result, 'env_runners', 'episode_return_max')

    # episode length
    len_mean = _get_any(result, ['episode_len_mean']) or \
               _get_nested(result, 'env_runners', 'episode_len_mean')
    len_min = _get_any(result, ['episode_len_min']) or \
              _get_nested(result, 'env_runners', 'episode_len_min')
    len_max = _get_any(result, ['episode_len_max']) or \
              _get_nested(result, 'env_runners', 'episode_len_max')

    # learner stats (DQN)
    learners = result.get('learners') or {}
    dp = learners.get('default_policy') or {}
    qf_loss = dp.get('qf_loss') or dp.get('total_loss')
    td_err = dp.get('td_error_mean')

    # throughput/steps/time
    steps_sampled = result.get('num_env_steps_sampled') or \
                    _get_nested(result, 'env_runners', 'num_env_steps_sampled') or \
                    _get_any(result, ['num_env_steps_sampled_lifetime'])
    time_this = result.get('time_this_iter_s')
    time_total = result.get('time_total_s')

    return {
        'iteration': iteration,
        'episode_return_mean': ret_mean,
        'episode_return_min': ret_min,
        'episode_return_max': ret_max,
        'episode_len_mean': len_mean,
        'episode_len_min': len_min,
        'episode_len_max': len_max,
        'qf_loss': qf_loss,
        'td_error_mean': td_err,
        'num_env_steps_sampled': steps_sampled,
        'time_this_iter_s': time_this,
        'time_total_s': time_total,
    }


class JesseRLEnvironment(gym.Env):
    """
    Jesse Reinforcement Learning Environment - Optimized for multi-core performance
    """
    
    def __init__(self, config: EnvContext):
        super().__init__()
        
        # Store configuration
        self.backtest_config = config.get('backtest_config')
        self.routes = config.get('routes')
        self.data_routes = config.get('data_routes')
        self.candles = config.get('candles')
        self.warmup_candles = config.get('warmup_candles')
        self.max_steps = config.get('max_steps', 1000)
        
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
        
        # Don't call reset() here - let Ray/RLlib call it when ready
    
    @property
    def action_space(self):
        return self._action_space
    
    @property 
    def observation_space(self):
        return self._observation_space
    
    def _get_strategy_instance_for_spaces(self):
        """Get strategy instance just for defining spaces (minimal setup)"""
        route = self.routes[0]
        strategy_name = route['strategy']
        
        # Import strategy class directly for space definitions
        StrategyClass = jh.get_strategy_class(strategy_name)
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
            'logging': {
                'balance_update': True,
                'order_cancellation': True,
                'order_execution': True,
                'order_submission': True,
                'position_closed': True,
                'position_increased': True,
                'position_opened': True,
                'position_reduced': True,
                'shorter_period_candles': False,
                'trading_candles': True
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
        
        # Initialize candle storage
        store.candles.init_storage(5000)
        
        # Validate candles only once (cache validation result)
        if not hasattr(self, '_candles_validated'):
            self._validate_candle_timeframes()
            self._candles_validated = True
        
        # OPTIMIZATION: Use shallow copy instead of deep copy for large candle arrays
        # The candle data itself doesn't need to be modified, only the dict structure
        self.trading_candles_dict = {}
        for key, value in self.candles.items():
            self.trading_candles_dict[key] = {
                'exchange': value['exchange'],
                'symbol': value['symbol'],
                'candles': value['candles']  # Reference same array instead of copying
            }
        
        # Same optimization for warmup candles
        self.warmup_candles_dict = {}
        if self.warmup_candles:
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
                # No more candles; finalize episode
                finalize_simulation()
                obs = store.rl.get_observation() or np.zeros(self.observation_space.shape, dtype=self.observation_space.dtype)
                return obs, 0.0, True, True, {}
            
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
            print(f"==> ERROR in step: {e}")
            import traceback
            traceback.print_exc()
            # Return safe defaults (terminated=True, truncated=False)
            return np.zeros(self.observation_space.shape, dtype=self.observation_space.dtype), 0.0, True, False, {}


def _run_quick_evaluation_episode(trainer, config, routes, data_routes, candles, warmup_candles):
    """Run a single evaluation episode to extract current trading performance"""
    try:
        env = JesseRLEnvironment({
            'backtest_config': config,
            'routes': routes, 
            'data_routes': data_routes,
            'candles': candles,
            'warmup_candles': warmup_candles,
            'max_steps': 1000,
        })
        
        obs, info = env.reset()
        done = False
        truncated = False
        
        while not (done or truncated):
            # Use the newer Ray RLlib API for action computation
            try:
                # Try the new RLModule API first (Ray 2.8+)
                if hasattr(trainer, 'get_module'):
                    module = trainer.get_module()
                    action_dict = module.forward_inference({'obs': np.expand_dims(obs, axis=0)})
                    action = action_dict['actions'][0]  # Extract single action from batch
                else:
                    # Fallback to older API
                    action = trainer.compute_single_action(obs, explore=False)
            except (AttributeError, TypeError) as e:
                # If all else fails, try the deprecated method
                try:
                    action = trainer.compute_single_action(obs)
                except Exception:
                    # Last resort: random action
                    action = env.action_space.sample()
            
            obs, reward, done, truncated, info = env.step(action)
        
        # Extract trading metrics from completed episode
        trading_metrics = _extract_trading_metrics_from_episode()
        return trading_metrics
        
    except Exception as e:
        # Return safe defaults on any error, but don't spam debug output
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
            'starting_balance': 10000.0,
            'finishing_balance': 10000.0,
            'total_winning_trades': 0,
            'total_losing_trades': 0,
            'longs_percentage': 0.0,
            'shorts_percentage': 0.0,
        }


def _summarize_training_with_trading_metrics(result: dict, iteration: int, 
                                           episode_trading_metrics: list) -> dict:
    """Enhanced training summary that includes both RL and trading metrics"""
    
    # Get existing RL metrics
    rl_summary = _summarize_training_result(result, iteration)
    
    # Calculate trading metrics aggregation across recent episodes
    recent_episodes = episode_trading_metrics[-5:]  # Last 5 episodes
    if recent_episodes:
        avg_profit_pct = np.mean([ep['net_profit_percentage'] for ep in recent_episodes])
        avg_win_rate = np.mean([ep['win_rate'] for ep in recent_episodes])
        avg_trades = np.mean([ep['total_trades'] for ep in recent_episodes])
        avg_sharpe = np.mean([ep['sharpe_ratio'] for ep in recent_episodes if ep['sharpe_ratio'] != 0])
        avg_max_dd = np.mean([ep['max_drawdown'] for ep in recent_episodes])
        
        best_episode = max(recent_episodes, key=lambda x: x['net_profit_percentage'])
    else:
        avg_profit_pct = avg_win_rate = avg_trades = avg_sharpe = avg_max_dd = 0
        best_episode = {}
    
    # Combine RL and trading metrics
    enhanced_summary = rl_summary.copy()
    enhanced_summary.update({
        'trading_avg_profit_pct': avg_profit_pct,
        'trading_avg_win_rate': avg_win_rate,
        'trading_avg_trades': avg_trades,
        'trading_avg_sharpe': avg_sharpe,
        'trading_avg_max_drawdown': avg_max_dd,
        'best_recent_profit_pct': best_episode.get('net_profit_percentage', 0),
        'best_recent_win_rate': best_episode.get('win_rate', 0),
    })
    
    return enhanced_summary




def train_rl_agent(
    config: dict,
    routes: List[Dict[str, str]],
    data_routes: List[Dict[str, str]],
    candles: dict,
    warmup_candles: dict = None,
    algorithm: str = 'DQN',
    num_iterations: int = 100,
    num_workers: int = 2,
    checkpoint_freq: int = 10,
) -> dict:
    """
    Train reinforcement learning agent with enhanced trading metrics output
    
    Args:
        config: Backtest configuration
        routes: Trading routes
        data_routes: Data routes
        candles: Candle data
        warmup_candles: Warmup candle data
        algorithm: RL algorithm to use (currently only 'DQN')
        num_iterations: Number of training iterations
        num_workers: Number of worker processes
        checkpoint_freq: Checkpoint frequency
    
    Returns:
        Training results with summaries, trading metrics, and checkpoints
    """
    
    if algorithm != 'DQN':
        raise ValueError("Currently only DQN algorithm is supported")
    
    # Optimize Ray initialization for better CPU utilization
    if not ray.is_initialized():
        try:
            ray.init(
                num_cpus=num_workers + 2,  # +2 for trainer and evaluation processes
                object_store_memory=1000000000,  # 1GB object store
                ignore_reinit_error=True,
                log_to_driver=False,  # Reduce logging overhead
                local_mode=False  # Ensure multi-processing mode
            )
            jh.debug(f"Ray initialized with {num_workers + 2} CPUs for RL training")
        except Exception as e:
            jh.debug(f"Ray initialization failed: {e}, falling back to minimal config")
            ray.init(num_cpus=num_workers + 1, ignore_reinit_error=True)
    
    # Register environment
    tune.register_env("jesse_env", lambda config: JesseRLEnvironment(config))
    
    # Optimize batch sizes and rollout configuration for multi-core usage
    # Scale batch size with number of workers for better parallel utilization
    train_batch_size = max(32, num_workers * 16)  # At least 16 samples per worker
    rollout_fragment_length = max(50, 200 // num_workers)  # Distribute rollout work
    
    # Create optimized DQN configuration
    dqn_config = (
        DQNConfig()
        .environment(
            env="jesse_env",
            env_config={
                'backtest_config': config,
                'routes': routes,
                'data_routes': data_routes,
                'candles': candles,
                'warmup_candles': warmup_candles,
                'max_steps': 1000,
            }
        )
        .framework("torch")
        .env_runners(
            num_env_runners=num_workers,
            num_envs_per_env_runner=1,  # One environment per worker to avoid resource conflicts
            rollout_fragment_length=rollout_fragment_length,
        )
        .training(
            lr=0.0001,
            train_batch_size=train_batch_size,
            target_network_update_freq=500,
        ).learners(
            num_learners=1,
            num_gpus_per_learner=0,
        )
        .resources(
            num_cpus_for_main_process=2,  # Trainer gets 2 CPUs for neural network training
        )
    )
    
    # Create trainer
    trainer = dqn_config.build_algo()
    
    # Initialize performance monitoring
    perf_monitor = PerformanceMonitor(num_workers)
    perf_monitor.start_monitoring()
    
    # Enhanced Training loop with trading metrics
    results = []
    summaries = []
    checkpoints = []
    episode_trading_metrics = []  # Track trading performance per episode
    
    print(f"Starting RL Training with {num_workers} workers on {perf_monitor.cpu_count} CPU system...")
    training_start_time = time.time()
    
    for i in range(num_iterations):
        result = trainer.train()
        results.append(result)
        
        # Extract trading metrics from completed episodes (skip first few iterations)
        if i >= 2 and (i + 1) % 10 == 0:  # Start evaluation after a few iterations, then every 10 iterations
            try:
                eval_metrics = _run_quick_evaluation_episode(trainer, config, routes, data_routes, candles, warmup_candles)
                episode_trading_metrics.append(eval_metrics)
            except Exception as e:
                pass  # Continue silently without trading metrics for this iteration
        
        # Create enhanced summary
        s = _summarize_training_with_trading_metrics(result, i + 1, episode_trading_metrics)
        summaries.append(s)
        
        # Clean, concise logging that shows both RL and trading performance when available
        if episode_trading_metrics and len(episode_trading_metrics) > 0:
            recent_trading = episode_trading_metrics[-1]
            profit = recent_trading['net_profit_percentage']
            trades = recent_trading['total_trades']
            win_rate = recent_trading['win_rate']
            
            print(f"Iter {i+1:2d}/{num_iterations} | "
                  f"Profit: {profit:+.1f}% | "
                  f"Trades: {trades:2d} | "
                  f"Win Rate: {win_rate:.0f}% | "
                  f"RL Return: {_fmt(s['episode_return_mean'])} | "
                  f"Time: {_fmt(s['time_this_iter_s'])}s")
        else:
            # Simple output for initial iterations
            print(f"Iter {i+1:2d}/{num_iterations} | "
                  f"RL Return: {_fmt(s['episode_return_mean'])} | "
                  f"Q-Loss: {_fmt(s['qf_loss'], sci=True)} | "
                  f"Time: {_fmt(s['time_this_iter_s'])}s")
        
        # Save checkpoint quietly
        if (i + 1) % checkpoint_freq == 0:
            ckpt = trainer.save()
            # Extract actual path from checkpoint object
            if hasattr(ckpt, 'checkpoint') and hasattr(ckpt.checkpoint, 'path'):
                ckpt_path = ckpt.checkpoint.path
            elif hasattr(ckpt, 'path'):
                ckpt_path = ckpt.path
            else:
                ckpt_path = "Unknown path"
            checkpoints.append(ckpt_path)
    
    # Stop performance monitoring and get summary
    perf_stats = perf_monitor.stop_monitoring()
    training_duration = time.time() - training_start_time
    
    # Enhanced final summary with trading metrics and performance stats
    print(f"\nTraining Complete! Duration: {training_duration:.1f}s")
    
    # Performance analysis
    if perf_stats:
        print(f"\n==> PERFORMANCE ANALYSIS:")
        print(f"    CPU Usage:     {perf_stats['avg_cpu_percent']:.1f}% avg, {perf_stats['max_cpu_percent']:.1f}% peak")
        print(f"    Expected CPU:  {perf_stats['expected_cpu_percent']:.1f}% ({perf_stats['workers_used']} workers / {perf_stats['total_cpus']} CPUs)")
        print(f"    CPU Efficiency: {perf_stats['cpu_efficiency']:.1%} (should be close to 100%)")
        print(f"    Memory Usage:  {perf_stats['avg_memory_percent']:.1f}%")
        
        if perf_stats['cpu_efficiency'] < 0.7:
            print(f"    ⚠️  Low CPU efficiency detected! Potential bottlenecks:")
            print(f"       - Jesse store operations might not parallelize well")
            print(f"       - Consider reducing batch complexity or optimizing environment")
        elif perf_stats['cpu_efficiency'] > 0.9:
            print(f"    ✅ Excellent CPU utilization!")
    
    if episode_trading_metrics:
        best_episode = max(episode_trading_metrics, key=lambda x: x['net_profit_percentage'])
        final_episode = episode_trading_metrics[-1]
        
        print(f"\n==> TRADING PERFORMANCE:")
        print(f"    Best Episode:   {best_episode['net_profit_percentage']:+.1f}% profit")
        print(f"    Final Episode:  {final_episode['net_profit_percentage']:+.1f}% profit")
        print(f"    Final Win Rate: {final_episode['win_rate']:.0f}%")
        
    if summaries:
        best_summary = max(summaries, key=lambda x: (float(x['episode_return_mean']) if x['episode_return_mean'] is not None else -1e18))
        final_summary = summaries[-1]
        
        print(f"\n==> RL LEARNING:")
        print(f"    Best RL Return:  {_fmt(best_summary['episode_return_mean'])}")
        print(f"    Final RL Return: {_fmt(final_summary['episode_return_mean'])}")
        print(f"    Final Q-Loss:    {_fmt(final_summary['qf_loss'], sci=True)}")
    
    # Clean up
    trainer.stop()
    ray.shutdown()
    
    return {
        'results': results,
        'summaries': summaries,
        'checkpoints': checkpoints,
        'episode_trading_metrics': episode_trading_metrics,
        'performance_stats': perf_stats,
        'training_duration': training_duration,
        'final_result': results[-1] if results else None
    }


def evaluate_rl_agent(
    config: dict,
    routes: List[Dict[str, str]],
    data_routes: List[Dict[str, str]],
    candles: dict,
    checkpoint_path: str,
    warmup_candles: dict = None,
    algorithm: str = 'DQN',
    num_episodes: int = 10,
) -> dict:
    """
    Evaluate trained RL agent
    
    Args:
        config: Backtest configuration
        routes: Trading routes
        data_routes: Data routes
        candles: Candle data
        checkpoint_path: Path to model checkpoint
        warmup_candles: Warmup candle data
        algorithm: RL algorithm used
        num_episodes: Number of evaluation episodes
    
    Returns:
        Evaluation results
    """
    
    if algorithm != 'DQN':
        raise ValueError("Currently only DQN algorithm is supported")
    
    # Initialize Ray
    if not ray.is_initialized():
        ray.init()
    
    # Register environment
    tune.register_env("jesse_env", lambda config: JesseRLEnvironment(config))
    
    # Create DQN configuration
    dqn_config = (
        DQNConfig()
        .environment(
            env="jesse_env",
            env_config={
                'backtest_config': config,
                'routes': routes,
                'data_routes': data_routes,
                'candles': candles,
                'warmup_candles': warmup_candles,
                'max_steps': 1000,
            }
        )
        .framework("torch")
    )
    
    # Create trainer and restore checkpoint
    trainer = dqn_config.build_algo()
    trainer.restore(checkpoint_path)
    
    # Evaluation
    episode_rewards = []
    
    for episode in range(num_episodes):
        env = JesseRLEnvironment({
            'backtest_config': config,
            'routes': routes,
            'data_routes': data_routes,
            'candles': candles,
            'warmup_candles': warmup_candles,
            'max_steps': 1000,
        })
        
        obs, info = env.reset()
        done = False
        truncated = False
        episode_reward = 0
        
        while not (done or truncated):
            # Use the newer RLlib API to avoid deprecation warnings
            try:
                # Try new API first
                action = trainer.compute_single_action(obs)
            except TypeError:
                # Fallback for older versions
                action = trainer.compute_single_action(obs, deterministic=True)
            obs, reward, done, truncated, info = env.step(action)
            episode_reward += reward
        
        episode_rewards.append(episode_reward)
        jh.debug(f"Episode {episode+1} reward: {episode_reward:.2f}")
    
    # Clean up
    trainer.stop()
    ray.shutdown()
    
    return {
        'episode_rewards': episode_rewards,
        'mean_reward': np.mean(episode_rewards),
        'std_reward': np.std(episode_rewards),
        'min_reward': np.min(episode_rewards),
        'max_reward': np.max(episode_rewards),
    }
