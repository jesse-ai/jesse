from typing import List, Dict, Any
import ray
import jesse.helpers as jh
import jesse.services.logger as logger

# =============================================================================
# SHARED CONSTANTS
# =============================================================================

# CPU and performance constants
DEFAULT_CPU_USAGE_RATIO = 0.8  # Use 80% of available CPU cores by default
MIN_CPU_CORES = 1  # Minimum number of CPU cores to use
RAY_WAIT_TIMEOUT = 0.5  # Timeout for Ray wait operations (seconds)

# Random seed constants
BASE_RANDOM_SEED = 42  # Base seed for reproducible results

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
# SHARED UTILITIES
# =============================================================================

def _setup_progress_bar(progress_bar: bool, total_scenarios: int, description: str):
    if not progress_bar:
        return None
    if jh.is_notebook():
        from tqdm.notebook import tqdm
    else:
        from tqdm import tqdm
    return tqdm(total=total_scenarios, desc=description)


def _safe_log_message(message: str, pbar, is_error: bool = False) -> None:
    formatted_message = message
    if is_error:
        formatted_message = f"{'='*80}\n🚨 ERROR: {message}\n{'='*80}"
    
    if pbar:
        if jh.is_notebook():
            print(formatted_message)
        else:
            from tqdm import tqdm
            tqdm.write(formatted_message)
    
    if jh.app_mode() == 'monte-carlo':
        logger.log_monte_carlo(message if not is_error else f"ERROR: {message}", session_id=jh.get_session_id())


def _process_scenario_results(
    scenario_refs: List[Any],
    pbar,
    progress_callback=None,
    result_callback=None
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    remaining_refs = scenario_refs.copy()
    total_scenarios = len(scenario_refs)
    completed_count = 0
    
    while remaining_refs:
        completed_refs, remaining_refs = ray.wait(remaining_refs, num_returns=1, timeout=RAY_WAIT_TIMEOUT)
        for ref in completed_refs:
            try:
                response = ray.get(ref)
                if isinstance(response, dict) and 'result' in response:
                    if response['result'] is not None:
                        results.append(response['result'])
                        # Stream the result immediately to the caller (for progressive UI updates)
                        if result_callback is not None:
                            try:
                                result_callback(response['result'])
                            except Exception:
                                # Do not crash the loop due to callback errors
                                pass
                    if response.get('log'):
                        is_error = response.get('error', False)
                        _safe_log_message(response['log'], pbar, is_error=is_error)
                else:
                    results.append(response)
            except Exception as e:
                error_msg = f"Error processing scenario result: {str(e)}"
                _safe_log_message(error_msg, pbar, is_error=True)
            
            if pbar:
                pbar.update(1)
            
            # Call progress callback with actual completion count
            completed_count += 1
            if progress_callback:
                progress_callback(completed_count)
    
    return results


def _create_ray_shared_objects(
    config: dict,
    routes: List[Dict[str, str]],
    data_routes: List[Dict[str, str]],
    candles: dict,
    warmup_candles: dict,
    hyperparameters: dict
) -> Dict[str, Any]:
    return {
        'config': ray.put(config),
        'routes': ray.put(routes),
        'data_routes': ray.put(data_routes),
        'candles': ray.put(candles),
        'warmup_candles': ray.put(warmup_candles),
        'hyperparameters': ray.put(hyperparameters)
    }


