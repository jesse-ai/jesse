from typing import List, Dict, Any
import ray
import jesse.helpers as jh

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


def _safe_log_message(message: str, pbar) -> None:
    if pbar:
        if jh.is_notebook():
            print(message)
        else:
            from tqdm import tqdm
            tqdm.write(message)
    else:
        jh.debug(message)


def _process_scenario_results(scenario_refs: List[Any], pbar) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    remaining_refs = scenario_refs.copy()
    while remaining_refs:
        completed_refs, remaining_refs = ray.wait(remaining_refs, num_returns=1, timeout=RAY_WAIT_TIMEOUT)
        for ref in completed_refs:
            try:
                response = ray.get(ref)
                if isinstance(response, dict) and 'result' in response:
                    if response['result'] is not None:
                        results.append(response['result'])
                    if response.get('log'):
                        _safe_log_message(response['log'], pbar)
                    if response.get('error', False):
                        error_msg = f"Error in scenario: {response.get('log', 'Unknown error')}"
                        _safe_log_message(error_msg, pbar)
                else:
                    results.append(response)
            except Exception as e:
                error_msg = f"Error processing scenario result: {str(e)}"
                _safe_log_message(error_msg, pbar)
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
    return {
        'config': ray.put(config),
        'routes': ray.put(routes),
        'data_routes': ray.put(data_routes),
        'candles': ray.put(candles),
        'warmup_candles': ray.put(warmup_candles),
        'hyperparameters': ray.put(hyperparameters)
    }


