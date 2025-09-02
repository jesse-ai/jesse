"""
Stress Test and Monte Carlo Simulation Module for Jesse Trading Framework

This module provides stress testing and Monte Carlo simulation capabilities for backtesting trading strategies.
It supports two types of simulations:
1. Stress Test: Uses different random candle data for each simulation to test strategy robustness
2. Monte Carlo: Shuffles the order of trades from an original backtest to test statistical significance

The module uses Ray for parallel processing to efficiently run multiple scenarios
simultaneously across multiple CPU cores.
"""

from typing import List, Dict, Literal, Optional, Tuple, Any, Union
import ray
from multiprocessing import cpu_count
import numpy as np
import random
import jesse.helpers as jh
from jesse.research import backtest

# =============================================================================
# CONSTANTS
# =============================================================================

# CPU and performance constants
DEFAULT_CPU_USAGE_RATIO = 0.8  # Use 80% of available CPU cores by default
MIN_CPU_CORES = 1  # Minimum number of CPU cores to use
RAY_WAIT_TIMEOUT = 0.5  # Timeout for Ray wait operations (seconds)

# Random seed constants
BASE_RANDOM_SEED = 42  # Base seed for reproducible results

# Validation constants
# Note: VALID_SIMULATION_TYPES removed as we now have separate functions

# Statistical constants
ANNUALIZATION_FACTOR = 365  # Trading days per year for volatility calculation
MAX_DRAWDOWN_LIMIT = 1.0  # Maximum possible drawdown (100%)

# Confidence interval percentiles
CONFIDENCE_PERCENTILES = {
    'extreme_low': 2.5,
    'low': 5,
    'low_quartile': 25,
    'median': 50,
    'high_quartile': 75,
    'high': 95,
    'extreme_high': 97.5
}

# Statistical significance levels
ALPHA_5_PERCENT = 0.05
ALPHA_1_PERCENT = 0.01

# =============================================================================
# RAY REMOTE FUNCTIONS
# =============================================================================

@ray.remote
def ray_run_scenario_stress_test(
    config: dict,
    routes: List[Dict[str, str]],
    data_routes: List[Dict[str, str]],
    candles: dict,
    warmup_candles: dict,
    hyperparameters: dict,
    fast_mode: bool,
    benchmark: bool,
    scenario_index: int,
    candles_pipeline_class = None,
    candles_pipeline_kwargs: dict = None
) -> Dict[str, Any]:
    """
    Ray remote function to execute a single stress test scenario.
    
    This function runs in a separate process and executes a backtest with potentially
    modified candle data based on the provided pipeline configuration. The first scenario
    in a benchmark run uses original data, while subsequent scenarios use the pipeline
    to modify the candle data for robustness testing.
    
    Args:
        config: Jesse configuration dictionary containing strategy and environment settings
        routes: List of trading routes, each containing exchange, symbol, timeframe, and strategy
        data_routes: List of data routes for additional data feeds required by the strategy
        candles: Dictionary containing historical candle data for all symbols and timeframes
        warmup_candles: Dictionary containing warmup period candle data for strategy initialization
        hyperparameters: Dictionary of strategy hyperparameters to use for this scenario
        fast_mode: Whether to run in fast mode (reduces some calculations for speed)
        benchmark: Whether this simulation includes a benchmark scenario (original data)
        scenario_index: Index of this scenario (used for logging, debugging, and benchmark detection)
        candles_pipeline_class: Optional class for modifying candle data (e.g., bootstrap, noise injection)
        candles_pipeline_kwargs: Arguments to pass to the candles pipeline class constructor
    
    Returns:
        Dictionary containing:
        - result: Backtest result dictionary or None if the scenario failed
        - log: Log message string or None if no issues occurred
        - error: Boolean indicating whether an error occurred during execution
        
    Note:
        This function is designed to be executed remotely by Ray workers. It handles
        all exceptions internally and returns structured results for centralized processing.
    """
    try:
        # Determine if this scenario should use the candles pipeline
        # Benchmark scenarios (index 0) always use original data when benchmark=True
        is_benchmark_scenario = benchmark and scenario_index == 0
        should_use_pipeline = candles_pipeline_class is not None and not is_benchmark_scenario

        # Execute the backtest for this specific scenario
        result = backtest(
            config=config,
            routes=routes,
            data_routes=data_routes,
            candles=candles,
            warmup_candles=warmup_candles,
            generate_equity_curve=True,  # Required for Monte Carlo analysis
            hyperparameters=hyperparameters,
            fast_mode=fast_mode,
            benchmark=is_benchmark_scenario,
            candles_pipeline_class=candles_pipeline_class if should_use_pipeline else None,
            candles_pipeline_kwargs=candles_pipeline_kwargs if should_use_pipeline else None
        )
        
        # Validate that the result contains an equity curve (required for analysis)
        if 'equity_curve' not in result or result['equity_curve'] is None:
            return {
                'result': result, 
                'log': f"Info: Scenario {scenario_index} missing equity_curve - will be filtered out",
                'error': False
            }
                
        return {'result': result, 'log': None, 'error': False}
        
    except Exception as e:
        # Import traceback for detailed error information
        import traceback
        
        # Capture full exception details for better debugging
        full_traceback = traceback.format_exc()
        error_type = type(e).__name__
        error_msg = str(e)
        
        # Create detailed error message
        detailed_error = (
            f"Ray scenario {scenario_index} failed:\n"
            f"Error Type: {error_type}\n"
            f"Error Message: {error_msg}\n"
            f"Full Traceback:\n{full_traceback}"
        )
        
        return {'result': None, 'log': detailed_error, 'error': True}

@ray.remote
def ray_run_scenario_monte_carlo(
    original_trades: list,
    original_equity_curve: list,
    starting_balance: float,
    scenario_index: int,
    seed: Optional[int] = None
) -> Dict[str, Any]:
    """
    Ray remote function to execute a single Monte Carlo scenario.
    
    This function performs Monte Carlo analysis by randomly reordering the
    trades from an original backtest and reconstructing the resulting equity curve.
    This helps assess how much of the strategy's performance is due to the specific
    timing of trades versus the trade selection itself.
    
    Args:
        original_trades: List of trade dictionaries from the original backtest, each containing
                        trade details including PNL, entry/exit times, and other metrics
        original_equity_curve: List containing the original equity curve data structure
                              with timestamps and portfolio values for temporal reference
        starting_balance: Initial account balance used to reconstruct the equity curve
        scenario_index: Index of this scenario (used for seeding random generators and logging)
        seed: Optional base seed for random number generation. If provided, will be combined
              with scenario_index to ensure reproducible but varied results across scenarios
    
    Returns:
        Dictionary containing:
        - result: Simulation result with calculated metrics and data, or None if failed
        - log: Log message string or None if no issues occurred  
        - error: Boolean indicating whether an error occurred during execution
        
    Note:
        The function maintains reproducibility by seeding random number generators while
        ensuring each scenario gets different random shuffling through scenario_index offset.
    """
    try:
        # Set up reproducible random number generation for this scenario
        if seed is not None:
            # Use base seed plus scenario index to ensure reproducible but varied results
            scenario_seed = seed + scenario_index
            random.seed(scenario_seed)
            np.random.seed(scenario_seed)
        
        # Create a shuffled copy of the trades (preserves original order)
        shuffled_trades = original_trades.copy()
        random.shuffle(shuffled_trades)
        
        # Reconstruct the equity curve with trades in new chronological order
        equity_curve = _reconstruct_equity_curve_from_trades(
            shuffled_trades, original_equity_curve, starting_balance
        )
        
        # Calculate performance metrics from the shuffled equity curve
        result = _calculate_metrics_from_equity_curve(equity_curve, starting_balance)
        
        # Include the shuffled trade data and equity curve in results
        result['trades'] = shuffled_trades
        result['equity_curve'] = equity_curve
        
        return {'result': result, 'log': None, 'error': False}
        
    except Exception as e:
        # Return structured error information for centralized handling
        error_msg = f"Ray Monte Carlo scenario {scenario_index} failed with exception: {str(e)}"
        return {'result': None, 'log': error_msg, 'error': True}

# =============================================================================
# MAIN MONTE CARLO FUNCTION
# =============================================================================

def stress_test(
    config: dict,
    routes: List[Dict[str, str]],
    data_routes: List[Dict[str, str]],
    candles: dict,
    warmup_candles: Optional[dict] = None,
    benchmark: bool = False,
    hyperparameters: Optional[dict] = None,
    fast_mode: bool = True,
    num_scenarios: int = 1000,
    progress_bar: bool = False,
    candles_pipeline_class = None,
    candles_pipeline_kwargs: Optional[dict] = None,
    cpu_cores: Optional[int] = None,
) -> dict:
    """
    Execute stress test simulation for trading strategy backtesting.
    
    This function runs multiple scenarios of a trading strategy using
    randomized candle data to assess the robustness of the strategy's performance
    across different market conditions.
    
    Args:
        config: Jesse configuration dictionary containing strategy and environment settings.
               Must include keys like 'starting_balance', exchanges, and other backtest settings.
        routes: List of trading routes, each containing:
               - exchange: Name of the exchange (e.g., 'Binance')
               - symbol: Trading pair symbol (e.g., 'BTC-USDT')  
               - timeframe: Candle timeframe (e.g., '1h', '4h', '1D')
               - strategy: Name of the strategy class to test
        data_routes: List of data routes for additional data feeds required by the strategy.
                    Can be empty if strategy only needs main route data.
        candles: Dictionary containing historical candle data for all symbols and timeframes.
                Structure: {exchange: {symbol: {timeframe: numpy_array}}}
        warmup_candles: Optional dictionary containing warmup period candle data for strategy
                       initialization. Uses same structure as main candles.
        benchmark: Whether to include a benchmark scenario using original unmodified data.
        hyperparameters: Optional dictionary of strategy hyperparameters. If None, uses
                        strategy defaults.
        fast_mode: Whether to run in fast mode (reduces some calculations for speed).
                  Recommended for large stress test runs.
        num_scenarios: Number of stress test scenarios to execute. Higher numbers provide
                      better statistical confidence but take longer to run.
        progress_bar: Whether to display a progress bar during execution. Useful for
                     long-running simulations.
        candles_pipeline_class: Optional class for modifying candle data in stress test simulation.
                               Must implement Jesse's candles pipeline interface. Examples:
                               MovingBlockBootstrap, GaussianNoise, etc.
        candles_pipeline_kwargs: Arguments to pass to the candles pipeline class constructor.
        cpu_cores: Number of CPU cores to use for parallel processing. If None, uses 80%
                  of available cores. Limited to available system cores.
    
    Returns:
        Dictionary containing stress test results:
        - type: "stress_test"
        - scenarios: List of backtest results from each scenario
        - num_scenarios: Number of successful scenarios completed
        - total_requested: Total number of scenarios requested
    
    Raises:
        RuntimeError: If Ray initialization fails or system doesn't have sufficient resources
    
    Examples:
        # Basic stress test with bootstrap pipeline
        result = stress_test(
            config=config,
            routes=[{'exchange': 'Binance', 'symbol': 'BTC-USDT', 'timeframe': '1h', 'strategy': 'MyStrategy'}],
            data_routes=[],
            candles=candles_data,
            num_scenarios=500,
            candles_pipeline_class=MovingBlockBootstrap,
            progress_bar=True
        )
        
        # Quick stress test with custom CPU allocation
        result = stress_test(
            config=config,
            routes=routes,
            data_routes=data_routes, 
            candles=candles_data,
            num_scenarios=100,
            cpu_cores=4,
            fast_mode=True
        )
    
    Note:
        - Ray is automatically initialized and cleaned up by this function
        - Results are processed in real-time as scenarios complete
        - Invalid scenarios (missing equity curves) are automatically filtered out
    """
    
    # Determine optimal CPU core allocation
    if cpu_cores is None:
        available_cores = cpu_count()
        # Use default percentage of available cores, but ensure at least 1
        cpu_cores = max(MIN_CPU_CORES, int(available_cores * DEFAULT_CPU_USAGE_RATIO))
    else:
        # Respect user preference but enforce reasonable limits
        available_cores = cpu_count()
        cpu_cores = max(MIN_CPU_CORES, min(cpu_cores, available_cores))

    # Initialize Ray for parallel processing if not already running
    ray_started_here = False
    if not ray.is_initialized():
        try:
            ray.init(num_cpus=cpu_cores, ignore_reinit_error=True)
            jh.debug(f"Successfully started Monte Carlo simulation with {cpu_cores} CPU cores")
            ray_started_here = True
        except Exception as e:
            raise RuntimeError(f"Error initializing Ray: {e}")

    try:
        # Execute stress test simulation
        return _run_stress_test_simulation(
            config, routes, data_routes, candles, warmup_candles, 
            benchmark, hyperparameters, fast_mode, num_scenarios, 
            progress_bar, candles_pipeline_class, candles_pipeline_kwargs, 
            cpu_cores, ray_started_here
        )
    
    except Exception as e:
        jh.debug(f"Error during Monte Carlo simulation: {e}")
        raise
    
    finally:
        # Clean up Ray resources only if we initialized it
        if ray_started_here and ray.is_initialized():
            ray.shutdown()


def monte_carlo(
    config: dict,
    routes: List[Dict[str, str]],
    data_routes: List[Dict[str, str]],
    candles: dict,
    warmup_candles: Optional[dict] = None,
    benchmark: bool = False,
    hyperparameters: Optional[dict] = None,
    fast_mode: bool = True,
    num_scenarios: int = 1000,
    progress_bar: bool = False,
    cpu_cores: Optional[int] = None,
) -> dict:
    """
    Execute Monte Carlo simulation for trading strategy backtesting.
    
    This function runs multiple scenarios of a trading strategy by shuffling
    trade orders to assess the statistical significance of the strategy's performance.
    
    Args:
        config: Jesse configuration dictionary containing strategy and environment settings.
               Must include keys like 'starting_balance', exchanges, and other backtest settings.
        routes: List of trading routes, each containing:
               - exchange: Name of the exchange (e.g., 'Binance')
               - symbol: Trading pair symbol (e.g., 'BTC-USDT')  
               - timeframe: Candle timeframe (e.g., '1h', '4h', '1D')
               - strategy: Name of the strategy class to test
        data_routes: List of data routes for additional data feeds required by the strategy.
                    Can be empty if strategy only needs main route data.
        candles: Dictionary containing historical candle data for all symbols and timeframes.
                Structure: {exchange: {symbol: {timeframe: numpy_array}}}
        warmup_candles: Optional dictionary containing warmup period candle data for strategy
                       initialization. Uses same structure as main candles.
        benchmark: Whether to include a benchmark scenario using original unmodified data.
        hyperparameters: Optional dictionary of strategy hyperparameters. If None, uses
                        strategy defaults.
        fast_mode: Whether to run in fast mode (reduces some calculations for speed).
                  Recommended for large Monte Carlo runs.
        num_scenarios: Number of Monte Carlo scenarios to execute. Higher numbers provide
                      better statistical confidence but take longer to run.
        progress_bar: Whether to display a progress bar during execution. Useful for
                     long-running simulations.
        cpu_cores: Number of CPU cores to use for parallel processing. If None, uses 80%
                  of available cores. Limited to available system cores.
    
    Returns:
        Dictionary containing Monte Carlo results:
        - type: "monte_carlo"  
        - original: Original backtest result used as baseline
        - scenarios: List of trade-shuffled scenario results
        - confidence_analysis: Statistical analysis including p-values and confidence intervals
        - num_scenarios: Number of successful scenarios completed
        - total_requested: Total number of scenarios requested
    
    Raises:
        RuntimeError: If Ray initialization fails or system doesn't have sufficient resources
        ValueError: If the original backtest doesn't contain trades data
    
    Examples:
        # Monte Carlo analysis for statistical significance
        result = monte_carlo(
            config=config,
            routes=[{'exchange': 'Binance', 'symbol': 'BTC-USDT', 'timeframe': '1h', 'strategy': 'MyStrategy'}],
            data_routes=[],
            candles=candles_data,
            num_scenarios=1000,
            progress_bar=True
        )
        
        # Quick Monte Carlo test with custom CPU allocation
        result = monte_carlo(
            config=config,
            routes=routes,
            data_routes=data_routes, 
            candles=candles_data,
            num_scenarios=100,
            cpu_cores=4,
            fast_mode=True
        )
    
    Note:
        - Ray is automatically initialized and cleaned up by this function
        - Results are processed in real-time as scenarios complete
        - The original backtest must contain trades data for this analysis
        - Trade timing is randomized while preserving individual trade results
    """
    # Determine optimal CPU core allocation
    if cpu_cores is None:
        available_cores = cpu_count()
        # Use default percentage of available cores, but ensure at least 1
        cpu_cores = max(MIN_CPU_CORES, int(available_cores * DEFAULT_CPU_USAGE_RATIO))
    else:
        # Respect user preference but enforce reasonable limits
        available_cores = cpu_count()
        cpu_cores = max(MIN_CPU_CORES, min(cpu_cores, available_cores))

    # Initialize Ray for parallel processing if not already running
    ray_started_here = False
    if not ray.is_initialized():
        try:
            ray.init(num_cpus=cpu_cores, ignore_reinit_error=True)
            jh.debug(f"Successfully started Monte Carlo simulation with {cpu_cores} CPU cores")
            ray_started_here = True
        except Exception as e:
            raise RuntimeError(f"Error initializing Ray: {e}")

    try:
        # Execute Monte Carlo simulation
        return _run_monte_carlo_simulation(
            config, routes, data_routes, candles, warmup_candles,
            benchmark, hyperparameters, fast_mode, num_scenarios, progress_bar,
            cpu_cores, ray_started_here
        )
    
    except Exception as e:
        jh.debug(f"Error during Monte Carlo simulation: {e}")
        raise
    
    finally:
        # Clean up Ray resources only if we initialized it
        if ray_started_here and ray.is_initialized():
            ray.shutdown()


# =============================================================================
# HELPER FUNCTIONS - VALIDATION AND SETUP
# =============================================================================

def _setup_progress_bar(progress_bar: bool, total_scenarios: int, description: str):
    """
    Set up progress bar for tracking simulation progress.
    
    Args:
        progress_bar: Whether to create a progress bar
        total_scenarios: Total number of scenarios to track
        description: Description to display with the progress bar
    
    Returns:
        Progress bar object or None if not requested
    """
    if not progress_bar:
        return None
    
    # Choose appropriate tqdm implementation based on environment
    if jh.is_notebook():
        from tqdm.notebook import tqdm
    else:
        from tqdm import tqdm
    
    return tqdm(total=total_scenarios, desc=description)


def _safe_log_message(message: str, pbar) -> None:
    """
    Log a message safely without interfering with the progress bar.
    
    Args:
        message: Message to log
        pbar: Progress bar object or None
    """
    if pbar:
        if jh.is_notebook():
            print(message)
        else:
            # Use tqdm.write to avoid interfering with progress bar
            from tqdm import tqdm
            tqdm.write(message)
    else:
        jh.debug(message)


def _process_scenario_results(scenario_refs: List[Any], pbar) -> List[Dict[str, Any]]:
    """
    Process Monte Carlo scenario results as they complete, with progress tracking.
    
    This function uses Ray's wait functionality to process results as soon as they're
    available, providing real-time feedback through the progress bar and error logging.
    
    Args:
        scenario_refs: List of Ray remote function references
        pbar: Progress bar object or None
    
    Returns:
        List of successful scenario results
    """
    results = []
    remaining_refs = scenario_refs.copy()
    
    # Process results as they become available
    while remaining_refs:
        # Wait for any scenario to complete (non-blocking with timeout)
        completed_refs, remaining_refs = ray.wait(
            remaining_refs, num_returns=1, timeout=RAY_WAIT_TIMEOUT
        )
        
        # Process all completed scenarios
        for ref in completed_refs:
            try:
                response = ray.get(ref)
                
                # Handle response based on structure
                if isinstance(response, dict) and 'result' in response:
                    # Add successful results to our collection
                    if response['result'] is not None:
                        results.append(response['result'])
                    
                    # Log any messages without interfering with progress bar
                    if response.get('log'):
                        _safe_log_message(response['log'], pbar)
                    
                    # Handle and log errors
                    if response.get('error', False):
                        error_msg = f"Error in scenario: {response.get('log', 'Unknown error')}"
                        _safe_log_message(error_msg, pbar)
                else:
                    # Handle legacy response format for backward compatibility
                    results.append(response)
                    
            except Exception as e:
                error_msg = f"Error processing scenario result: {str(e)}"
                _safe_log_message(error_msg, pbar)
            
            # Update progress indicator
            if pbar:
                pbar.update(1)
    
    return results


def _create_ray_shared_objects(
    config: dict, 
    routes: List[Dict[str, str]], 
    data_routes: List[Dict[str, str]], 
    candles: dict, 
    warmup_candles: dict, 
    hyperparameters: dict
) -> Dict[str, Any]:
    """
    Store large objects in Ray's shared memory for efficient access across workers.
    
    Args:
        config: Configuration dictionary
        routes: Trading routes
        data_routes: Data routes
        candles: Candle data
        warmup_candles: Warmup candle data
        hyperparameters: Strategy hyperparameters
    
    Returns:
        Dictionary containing Ray object references
    """
    return {
        'config': ray.put(config),
        'routes': ray.put(routes),
        'data_routes': ray.put(data_routes),
        'candles': ray.put(candles),
        'warmup_candles': ray.put(warmup_candles),
        'hyperparameters': ray.put(hyperparameters)
    }


def _launch_stress_test_scenarios(
    num_scenarios: int,
    shared_objects: Dict[str, Any],
    fast_mode: bool,
    benchmark: bool,
    candles_pipeline_class,
    candles_pipeline_kwargs: dict
) -> List[Any]:
    """
    Launch all stress test scenarios in parallel.
    
    Args:
        num_scenarios: Number of scenarios to launch
        shared_objects: Dictionary of Ray shared object references
        fast_mode: Whether to use fast mode
        benchmark: Whether to include benchmark scenario
        candles_pipeline_class: Class for modifying candle data in stress test
        candles_pipeline_kwargs: Arguments for pipeline class
    
    Returns:
        List of Ray remote function references
    """
    scenario_refs = []
    
    for i in range(num_scenarios):
        ref = ray_run_scenario_stress_test.remote(
            config=shared_objects['config'],
            routes=shared_objects['routes'],
            data_routes=shared_objects['data_routes'],
            candles=shared_objects['candles'],
            warmup_candles=shared_objects['warmup_candles'],
            hyperparameters=shared_objects['hyperparameters'],
            fast_mode=fast_mode,
            benchmark=benchmark,
            scenario_index=i,
            candles_pipeline_class=candles_pipeline_class,
            candles_pipeline_kwargs=candles_pipeline_kwargs
        )
        scenario_refs.append(ref)
    
    return scenario_refs


def _filter_valid_results(results: List[dict]) -> Tuple[List[dict], int]:
    """
    Filter out results that don't contain valid equity curves.
    
    Args:
        results: List of scenario results
    
    Returns:
        Tuple of (valid_results, filtered_count)
    """
    valid_results = [
        r for r in results 
        if 'equity_curve' in r and r['equity_curve'] is not None
    ]
    filtered_count = len(results) - len(valid_results)
    
    return valid_results, filtered_count


def _log_stress_test_simulation_summary(valid_results: List[dict], filtered_count: int, num_scenarios: int) -> None:
    """
    Log summary information for stress test simulation results.
    
    Args:
        valid_results: List of valid scenario results
        filtered_count: Number of filtered out scenarios
        num_scenarios: Total number of requested scenarios
    """
    if filtered_count > 0:
        jh.debug(f"Filtered out {filtered_count} scenarios with missing equity curves")
    
    jh.debug(f"Returned {len(valid_results)} valid scenarios out of {num_scenarios} total")


def _run_original_backtest(
    config: dict,
    routes: List[Dict[str, str]],
    data_routes: List[Dict[str, str]],
    candles: dict,
    warmup_candles: dict,
    hyperparameters: dict,
    fast_mode: bool,
    benchmark: bool
) -> dict:
    """
    Run the original backtest to extract trade data for shuffling.
    
    Args:
        config: Jesse configuration dictionary
        routes: Trading routes
        data_routes: Data routes
        candles: Candle data
        warmup_candles: Warmup candle data
        hyperparameters: Strategy hyperparameters
        fast_mode: Whether to use fast mode
        benchmark: Whether this is a benchmark run
    
    Returns:
        Original backtest result dictionary
    """
    return backtest(
        config=config,
        routes=routes,
        data_routes=data_routes,
        candles=candles,
        warmup_candles=warmup_candles,
        generate_equity_curve=True,
        hyperparameters=hyperparameters,
        fast_mode=fast_mode,
        benchmark=benchmark
        # Note: No candles_pipeline_class for original data
    )


def _extract_trade_data(original_result: dict, config: dict) -> Tuple[list, list, float]:
    """
    Extract and validate trade data from the original backtest result.
    
    Args:
        original_result: Result dictionary from original backtest
        config: Configuration dictionary containing starting balance
    
    Returns:
        Tuple of (trades_list, equity_curve, starting_balance)
    
    Raises:
        ValueError: If trade data is missing or invalid
    """
    # Validate that trades exist in the result
    if 'trades' not in original_result:
        available_keys = list(original_result.keys())
        jh.debug(f"Available keys in backtest result: {available_keys}")
        raise ValueError("No 'trades' key found in backtest result. Cannot perform trade-shuffling Monte Carlo.")
    
    trades_list = original_result['trades']
    
    # Check if trades list is empty and provide helpful diagnostic information
    if not trades_list:
        _diagnose_empty_trades(original_result)
        raise ValueError("No trades found in original backtest. Cannot perform trade-shuffling Monte Carlo.")
    
    # Extract other required data
    original_equity_curve = original_result['equity_curve']
    starting_balance = config.get('starting_balance', 10000)
    
    return trades_list, original_equity_curve, starting_balance


def _diagnose_empty_trades(original_result: dict) -> None:
    """
    Provide diagnostic information when no trades are found.
    
    Args:
        original_result: Original backtest result for diagnosis
    """
    jh.debug("Trades list is empty. This could happen if:")
    jh.debug("1. The strategy didn't generate any trades")
    jh.debug("2. The time period was too short")
    jh.debug("3. The strategy conditions were never met")
    
    if 'metrics' in original_result:
        total_trades = original_result['metrics'].get('total', 0)
        jh.debug(f"   Metrics shows total trades: {total_trades}")


def _launch_monte_carlo_scenarios(
    num_scenarios: int,
    trades_ref: Any,
    equity_curve_ref: Any,
    starting_balance: float
) -> List[Any]:
    """
    Launch all Monte Carlo scenarios in parallel.
    
    Args:
        num_scenarios: Number of scenarios to launch
        trades_ref: Ray reference to original trades data
        equity_curve_ref: Ray reference to original equity curve
        starting_balance: Initial account balance
    
    Returns:
        List of Ray remote function references
    """
    scenario_refs = []
    
    for i in range(num_scenarios):
        ref = ray_run_scenario_monte_carlo.remote(
            original_trades=trades_ref,
            original_equity_curve=equity_curve_ref,
            starting_balance=starting_balance,
            scenario_index=i,
            seed=BASE_RANDOM_SEED
        )
        scenario_refs.append(ref)
    
    return scenario_refs


# =============================================================================
# SIMULATION EXECUTION FUNCTIONS
# =============================================================================

def _run_stress_test_simulation(
    config: dict, routes: List[Dict[str, str]], data_routes: List[Dict[str, str]], 
    candles: dict, warmup_candles: dict, benchmark: bool, hyperparameters: dict, 
    fast_mode: bool, num_scenarios: int, progress_bar: bool, 
    candles_pipeline_class, candles_pipeline_kwargs: dict, cpu_cores: int, started_ray_here: bool
) -> dict:
    """
    Execute stress test simulation.
    
    This function runs multiple backtests where each scenario potentially uses
    modified candle data based on the provided pipeline. This helps assess
    how sensitive the strategy is to variations in market data.
    """
    try:
        # Initialize progress tracking
        pbar = _setup_progress_bar(progress_bar, num_scenarios, "Stress Test Scenarios")

        # Store large objects in Ray's shared memory for efficiency
        shared_objects = _create_ray_shared_objects(
            config, routes, data_routes, candles, warmup_candles, hyperparameters
        )

        # Launch all scenarios in parallel for maximum efficiency
        scenario_refs = _launch_stress_test_scenarios(
            num_scenarios, shared_objects, fast_mode, benchmark,
            candles_pipeline_class, candles_pipeline_kwargs
        )

        # Process results as they complete with real-time feedback
        results = _process_scenario_results(scenario_refs, pbar)
        
        if pbar:
            pbar.close()

        # Filter and validate results
        valid_results, filtered_count = _filter_valid_results(results)
        
        # Log summary information
        _log_stress_test_simulation_summary(valid_results, filtered_count, num_scenarios)
        
        return {
            'type': 'stress_test',
            'scenarios': valid_results,
            'num_scenarios': len(valid_results),
            'total_requested': num_scenarios
        }
    
    except Exception as e:
        print(f"Error during stress test simulation: {e}")
        raise

def _run_monte_carlo_simulation(
    config: dict, routes: List[Dict[str, str]], data_routes: List[Dict[str, str]], 
    candles: dict, warmup_candles: dict, benchmark: bool, hyperparameters: dict, fast_mode: bool, 
    num_scenarios: int, progress_bar: bool, cpu_cores: int, started_ray_here: bool
) -> dict:
    """
    Execute Monte Carlo simulation.
    
    This function first runs an original backtest to extract trades, then
    shuffles the order of these trades across multiple scenarios to analyze
    how trade timing affects performance metrics and statistical significance.
    """
    try:
        jh.debug("Running original backtest to extract trades...")
        
        # Execute original backtest to obtain trade history
        original_result = _run_original_backtest(
            config, routes, data_routes, candles, warmup_candles,
            hyperparameters, fast_mode, benchmark
        )
        
        # Extract and validate trade data
        original_trades, original_equity_curve, starting_balance = _extract_trade_data(
            original_result, config
        )
        
        # Initialize progress tracking
        pbar = _setup_progress_bar(progress_bar, num_scenarios, "Monte Carlo Scenarios")

        # Store shared objects in Ray's memory
        trades_ref = ray.put(original_trades)
        equity_curve_ref = ray.put(original_equity_curve)
        
        # Launch trade shuffling scenarios in parallel
        scenario_refs = _launch_monte_carlo_scenarios(
            num_scenarios, trades_ref, equity_curve_ref, starting_balance
        )

        # Process results as they complete
        results = _process_scenario_results(scenario_refs, pbar)
        
        if pbar:
            pbar.close()

        jh.debug(f"Completed {len(results)} Monte Carlo scenarios out of {num_scenarios} requested")
        
        # Perform statistical analysis on the results
        confidence_analysis = _calculate_confidence_intervals(original_result, results)
        
        return {
            'type': 'monte_carlo',
            'original': original_result,
            'scenarios': results,
            'confidence_analysis': confidence_analysis,
            'num_scenarios': len(results),
            'total_requested': num_scenarios
        }
    
    except Exception as e:
        print(f"Error during Monte Carlo simulation: {e}")
        raise


# =============================================================================
# EQUITY CURVE AND METRICS CALCULATION
# =============================================================================

def _reconstruct_equity_curve_from_trades(shuffled_trades: list, original_equity_curve: list, starting_balance: float) -> list:
    """
    Reconstruct an equity curve from shuffled trades.
    
    This function takes a shuffled list of trades and reconstructs what the equity
    curve would have looked like if those trades had occurred in that order, while
    maintaining the same time structure as the original equity curve. This is the
    core algorithm for trades-based Monte Carlo analysis.
    
    The algorithm distributes trades evenly across the time period to maintain
    temporal realism - trades aren't all clustered at the beginning or end.
    
    Args:
        shuffled_trades: List of trades in shuffled order
        original_equity_curve: Original equity curve for time structure reference
        starting_balance: Initial account balance
    
    Returns:
        New equity curve list with same structure as original
    
    Raises:
        ValueError: If original equity curve format is invalid
    """
    # Validate input equity curve format
    if not original_equity_curve or not original_equity_curve[0].get('data'):
        raise ValueError("Invalid original equity curve format")
    
    # Extract time structure from original equity curve
    # The equity curve is typically a list with Portfolio data as the first element
    original_data = original_equity_curve[0]['data']
    time_points = [item.get('time', item.get('timestamp', 0)) for item in original_data]
    
    # Initialize new equity curve with same structure as original
    new_equity_curve = [{
        'name': 'Portfolio',
        'data': []
    }]
    
    # Distribute trades evenly across the time period to maintain realism
    # This approach prevents clustering all trades at the beginning or end
    current_balance = starting_balance
    trade_index = 0
    
    # Calculate how many trades to execute by each time point
    # This creates a linear distribution of trade execution across time
    total_trades = len(shuffled_trades)
    total_time_points = len(time_points)
    trades_per_point = total_trades / total_time_points if total_time_points > 0 else 1
    
    # Build the equity curve by progressively adding trades at each time point
    for i, timestamp in enumerate(time_points):
        # Determine how many trades should be completed by this time point
        # Using cumulative distribution to ensure all trades are eventually included
        target_trades_completed = int((i + 1) * trades_per_point)
        trades_to_add = target_trades_completed - trade_index
        
        # Execute the calculated number of trades at this time point
        for _ in range(trades_to_add):
            if trade_index < total_trades:
                # Add the PNL of the next shuffled trade to the current balance
                current_balance += shuffled_trades[trade_index]['PNL']
                trade_index += 1
        
        # Record the portfolio value at this timestamp
        new_equity_curve[0]['data'].append({
            'time': timestamp,
            'value': current_balance
        })
    
    return new_equity_curve

def _calculate_metrics_from_equity_curve(equity_curve: list, starting_balance: float) -> dict:
    """
    Calculate comprehensive performance metrics from an equity curve.
    
    This function computes various trading performance metrics including returns,
    risk measures, and risk-adjusted return ratios from equity curve data.
    
    Args:
        equity_curve: List containing equity curve data
        starting_balance: Initial account balance
    
    Returns:
        Dictionary containing calculated performance metrics
    """
    # Validate equity curve format
    if not equity_curve or not equity_curve[0].get('data'):
        return {'error': 'Invalid equity curve'}
    
    # Extract balance values from equity curve
    data = equity_curve[0]['data']
    values = [item['value'] for item in data]
    
    if not values:
        return {'error': 'No data in equity curve'}
    
    # Calculate basic return metrics
    final_value = values[-1]
    total_return = (final_value - starting_balance) / starting_balance
    
    # Calculate maximum drawdown with protection against extreme values
    max_drawdown = _calculate_max_drawdown(values)
    
    # Calculate volatility and risk-adjusted metrics
    volatility, sharpe_ratio = _calculate_volatility_metrics(values)
    
    # Calculate Calmar ratio (return per unit of maximum drawdown)
    calmar_ratio = total_return / max_drawdown if max_drawdown > 0 else 0
    
    return {
        'total_return': total_return,
        'final_value': final_value,
        'max_drawdown': max_drawdown,
        'volatility': volatility,
        'sharpe_ratio': sharpe_ratio,
        'calmar_ratio': calmar_ratio,
        'starting_balance': starting_balance
    }


def _calculate_max_drawdown(values: List[float]) -> float:
    """
    Calculate the maximum drawdown from a series of portfolio values.
    
    Maximum drawdown represents the largest peak-to-trough decline in portfolio value,
    expressed as a percentage of the peak value.
    
    Args:
        values: List of portfolio values over time
    
    Returns:
        Maximum drawdown as a decimal (0.0 to 1.0)
    """
    peak = values[0] if values else 0
    max_drawdown = 0.0
    
    for value in values:
        # Update peak if we have a new high
        if value > peak:
            peak = value
        
        # Calculate current drawdown and update maximum
        if peak > 0:
            current_drawdown = (peak - value) / peak
            # Cap drawdown at 100% (complete loss)
            current_drawdown = min(MAX_DRAWDOWN_LIMIT, current_drawdown)
            max_drawdown = max(max_drawdown, current_drawdown)
    
    return max_drawdown


def _calculate_volatility_metrics(values: List[float]) -> Tuple[float, float]:
    """
    Calculate volatility and Sharpe ratio from portfolio values.
    
    Args:
        values: List of portfolio values over time
    
    Returns:
        Tuple of (annualized_volatility, sharpe_ratio)
    """
    if len(values) <= 1:
        return 0.0, 0.0
    
    # Calculate daily returns, handling zero values safely
    returns = []
    for i in range(1, len(values)):
        if values[i-1] != 0:
            daily_return = (values[i] - values[i-1]) / values[i-1]
            returns.append(daily_return)
    
    if not returns:
        return 0.0, 0.0
    
    # Calculate annualized volatility
    daily_std = np.std(returns)
    annualized_volatility = daily_std * np.sqrt(ANNUALIZATION_FACTOR)
    
    # Calculate Sharpe ratio (assuming zero risk-free rate)
    avg_daily_return = np.mean(returns)
    annualized_return = avg_daily_return * ANNUALIZATION_FACTOR
    sharpe_ratio = annualized_return / annualized_volatility if annualized_volatility > 0 else 0
    
    return annualized_volatility, sharpe_ratio


# =============================================================================
# STATISTICAL ANALYSIS FUNCTIONS
# =============================================================================

def _calculate_confidence_intervals(original_result: dict, simulation_results: list) -> dict:
    """Calculate confidence intervals and statistical analysis"""
    if not simulation_results:
        return {'error': 'No simulation results to analyze'}
    
    # Extract metrics from all simulations
    # Remove final_value and volatility since they're not meaningful under trade shuffling
    metrics = {
        'total_return': [],
        'max_drawdown': [],
        'sharpe_ratio': [],
        'calmar_ratio': []
    }
    
    for result in simulation_results:
        for key in metrics.keys():
            if key in result and isinstance(result[key], (int, float)):
                metrics[key].append(result[key])
    
    # Use original backtest metrics directly instead of recalculating
    original_metrics = original_result.get('metrics', {})
    
    # Calculate percentiles and confidence intervals
    confidence_analysis = {}
    
    for metric_name, values in metrics.items():
        if not values:
            continue
            
        values_array = np.array(values)
        original_value = original_metrics.get(metric_name, 0)
        
        # Calculate percentiles
        percentiles = {
            '5th': np.percentile(values_array, 5),
            '25th': np.percentile(values_array, 25),
            '50th': np.percentile(values_array, 50),  # median
            '75th': np.percentile(values_array, 75),
            '95th': np.percentile(values_array, 95)
        }
        
        # Calculate confidence intervals
        ci_95 = {
            'lower': np.percentile(values_array, CONFIDENCE_PERCENTILES['extreme_low']),
            'upper': np.percentile(values_array, CONFIDENCE_PERCENTILES['extreme_high'])
        }
        
        ci_90 = {
            'lower': np.percentile(values_array, CONFIDENCE_PERCENTILES['low']),
            'upper': np.percentile(values_array, CONFIDENCE_PERCENTILES['high'])
        }
        
        # Calculate p-value (probability of getting original result or better by chance)
        if metric_name in ['total_return', 'sharpe_ratio', 'calmar_ratio']:
            # Higher is better
            p_value = np.sum(values_array >= original_value) / len(values_array)
        else:
            # Lower is better (max_drawdown)
            p_value = np.sum(values_array <= original_value) / len(values_array)
        
        # Calculate additional statistics
        mean_sim = np.mean(values_array)
        std_sim = np.std(values_array)
        
        confidence_analysis[metric_name] = {
            'original': original_value,
            'simulations': {
                'mean': mean_sim,
                'std': std_sim,
                'min': np.min(values_array),
                'max': np.max(values_array),
                'count': len(values_array)
            },
            'percentiles': percentiles,
            'confidence_intervals': {
                '90%': ci_90,
                '95%': ci_95
            },
            'p_value': p_value,
            'is_significant_5pct': p_value < ALPHA_5_PERCENT,
            'is_significant_1pct': p_value < ALPHA_1_PERCENT
        }
    
    # Overall summary
    summary = {
        'num_simulations': len(simulation_results),
        'significant_metrics_5pct': sum(1 for m in confidence_analysis.values() if m.get('is_significant_5pct', False)),
        'significant_metrics_1pct': sum(1 for m in confidence_analysis.values() if m.get('is_significant_1pct', False)),
        'total_metrics': len(confidence_analysis)
    }
    
    return {
        'summary': summary,
        'metrics': confidence_analysis,
        'interpretation': _generate_interpretation(confidence_analysis)
    }

def _generate_interpretation(confidence_analysis: dict) -> dict:
    """Generate human-readable interpretation of the results"""
    interpretations = []
    
    for metric_name, analysis in confidence_analysis.items():
        original = analysis['original']
        p_value = analysis['p_value']
        percentiles = analysis['percentiles']
        
        if analysis['is_significant_1pct']:
            significance = "highly significant (p < 0.01)"
        elif analysis['is_significant_5pct']:
            significance = "significant (p < 0.05)"
        else:
            significance = "not significant (p >= 0.05)"
        
        # Determine percentile rank of original result
        if original >= percentiles['95th']:
            rank = "top 5%"
        elif original >= percentiles['75th']:
            rank = "top 25%"
        elif original >= percentiles['50th']:
            rank = "above median"
        elif original >= percentiles['25th']:
            rank = "below median"
        else:
            rank = "bottom 25%"
        
        interpretations.append({
            'metric': metric_name,
            'significance': significance,
            'rank': rank,
            'p_value': p_value,
            'message': f"{metric_name}: {significance}, original result in {rank} of simulations"
        })
    
    return {
        'detailed': interpretations,
        'overall': f"Strategy shows {significance} performance with {len([i for i in interpretations if 'significant' in i['significance']])} out of {len(interpretations)} metrics being statistically significant."
    }
