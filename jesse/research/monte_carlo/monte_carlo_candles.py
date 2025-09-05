from typing import List, Dict, Optional, Tuple, Any, TypedDict
import ray
from multiprocessing import cpu_count
import jesse.helpers as jh
from jesse.research import backtest

from .common import (
    DEFAULT_CPU_USAGE_RATIO,
    MIN_CPU_CORES,
    _setup_progress_bar,
    _process_scenario_results,
    _create_ray_shared_objects,
)

# ============================================================================
# Typed return structures for candles-based Monte Carlo
# ============================================================================
class EquityCurvePoint(TypedDict):
    time: int
    value: float

class EquityCurveSeries(TypedDict):
    name: str
    data: List[EquityCurvePoint]

class MonteCarloCandlesScenarioResult(TypedDict, total=False):
    scenario_index: int
    metrics: Dict[str, Any]  # Backtest metrics dict
    equity_curve: List[EquityCurveSeries]
    trades: List[Dict[str, Any]]

class MonteCarloCandlesReturn(TypedDict):
    original: MonteCarloCandlesScenarioResult | None
    scenarios: List[MonteCarloCandlesScenarioResult]
    num_scenarios: int
    total_requested: int


@ray.remote
def ray_run_scenario_monte_carlo_candles(
    config: dict,
    routes: List[Dict[str, str]],
    data_routes: List[Dict[str, str]],
    candles: dict,
    warmup_candles: dict,
    hyperparameters: dict,
    fast_mode: bool,
    scenario_index: int,
    candles_pipeline_class = None,
    candles_pipeline_kwargs: dict = None
) -> Dict[str, Any]:
    """
    Ray remote function to execute a single Monte Carlo candles scenario.
    """
    try:
        # Always apply the pipeline for Monte Carlo scenarios (except scenario 0 which is original)
        should_use_pipeline = candles_pipeline_class is not None and scenario_index > 0
        result = backtest(
            config=config,
            routes=routes,
            data_routes=data_routes,
            candles=candles,
            warmup_candles=warmup_candles,
            generate_equity_curve=True,
            hyperparameters=hyperparameters,
            fast_mode=fast_mode,
            benchmark=False,  # Never use benchmark mode
            candles_pipeline_class=candles_pipeline_class if should_use_pipeline else None,
            candles_pipeline_kwargs=candles_pipeline_kwargs if should_use_pipeline else None
        )
        # Tag the result with its scenario index so downstream consumers can
        # reliably identify the original vs simulated scenarios regardless of completion order
        result['scenario_index'] = scenario_index
        if 'equity_curve' not in result or result['equity_curve'] is None:
            return {
                'result': result,
                'log': f"Info: Scenario {scenario_index} missing equity_curve - will be filtered out",
                'error': False
            }
        return {'result': result, 'log': None, 'error': False}
    except Exception as e:
        import traceback
        full_traceback = traceback.format_exc()
        error_type = type(e).__name__
        error_msg = str(e)
        detailed_error = (
            f"Ray scenario {scenario_index} failed:\n"
            f"Error Type: {error_type}\n"
            f"Error Message: {error_msg}\n"
            f"Full Traceback:\n{full_traceback}"
        )
        return {'result': None, 'log': detailed_error, 'error': True}


def monte_carlo_candles(
    config: dict,
    routes: List[Dict[str, str]],
    data_routes: List[Dict[str, str]],
    candles: dict,
    warmup_candles: Optional[dict] = None,
    hyperparameters: Optional[dict] = None,
    fast_mode: bool = True,
    num_scenarios: int = 1000,
    progress_bar: bool = False,
    candles_pipeline_class = None,
    candles_pipeline_kwargs: Optional[dict] = None,
    cpu_cores: Optional[int] = None,
) -> MonteCarloCandlesReturn:
    if cpu_cores is None:
        available_cores = cpu_count()
        cpu_cores = max(MIN_CPU_CORES, int(available_cores * DEFAULT_CPU_USAGE_RATIO))
    else:
        available_cores = cpu_count()
        cpu_cores = max(MIN_CPU_CORES, min(cpu_cores, available_cores))
    ray_started_here = False
    if not ray.is_initialized():
        try:
            ray.init(num_cpus=cpu_cores, ignore_reinit_error=True)
            print(f"Successfully started Monte Carlo simulation with {cpu_cores} CPU cores")
            ray_started_here = True
        except Exception as e:
            raise RuntimeError(f"Error initializing Ray: {e}")
    try:
        return _run_monte_carlo_candles_simulation(
            config, routes, data_routes, candles, warmup_candles,
            hyperparameters, fast_mode, num_scenarios,
            progress_bar, candles_pipeline_class, candles_pipeline_kwargs,
            cpu_cores, ray_started_here
        )
    except Exception as e:
        jh.debug(f"Error during Monte Carlo simulation: {e}")
        raise
    finally:
        if ray_started_here and ray.is_initialized():
            ray.shutdown()


def _launch_monte_carlo_candles_scenarios(
    num_scenarios: int,
    shared_objects: Dict[str, Any],
    fast_mode: bool,
    candles_pipeline_class,
    candles_pipeline_kwargs: dict
) -> List[Any]:
    scenario_refs = []
    for i in range(num_scenarios):
        ref = ray_run_scenario_monte_carlo_candles.remote(
            config=shared_objects['config'],
            routes=shared_objects['routes'],
            data_routes=shared_objects['data_routes'],
            candles=shared_objects['candles'],
            warmup_candles=shared_objects['warmup_candles'],
            hyperparameters=shared_objects['hyperparameters'],
            fast_mode=fast_mode,
            scenario_index=i,
            candles_pipeline_class=candles_pipeline_class,
            candles_pipeline_kwargs=candles_pipeline_kwargs
        )
        scenario_refs.append(ref)
    return scenario_refs


def _filter_valid_results(results: List[dict]) -> Tuple[List[dict], int]:
    valid_results = [
        r for r in results
        if 'equity_curve' in r and r['equity_curve'] is not None
    ]
    filtered_count = len(results) - len(valid_results)
    return valid_results, filtered_count


def _log_monte_carlo_candles_simulation_summary(valid_results: List[dict], filtered_count: int, num_scenarios: int) -> None:
    if filtered_count > 0:
        print(f"Filtered out {filtered_count} scenarios with missing equity curves")
    print(f"Returned {len(valid_results)} valid scenarios out of {num_scenarios} total")


def _run_monte_carlo_candles_simulation(
    config: dict, routes: List[Dict[str, str]], data_routes: List[Dict[str, str]],
    candles: dict, warmup_candles: dict, hyperparameters: dict,
    fast_mode: bool, num_scenarios: int, progress_bar: bool,
    candles_pipeline_class, candles_pipeline_kwargs: dict, cpu_cores: int, started_ray_here: bool
) -> dict:
    try:
        pbar = _setup_progress_bar(progress_bar, num_scenarios, "Monte Carlo Candles Scenarios")
        shared_objects = _create_ray_shared_objects(
            config, routes, data_routes, candles, warmup_candles, hyperparameters
        )
        scenario_refs = _launch_monte_carlo_candles_scenarios(
            num_scenarios, shared_objects, fast_mode,
            candles_pipeline_class, candles_pipeline_kwargs
        )
        results = _process_scenario_results(scenario_refs, pbar)
        if pbar:
            pbar.close()
        valid_results, filtered_count = _filter_valid_results(results)
        _log_monte_carlo_candles_simulation_summary(valid_results, filtered_count, num_scenarios)
        
        # Separate original result (scenario_index == 0) from Monte Carlo simulations
        original_result = next((r for r in valid_results if r.get('scenario_index') == 0), None)
        simulation_results = [r for r in valid_results if r.get('scenario_index', -1) > 0]
        
        return {
            'original': original_result,
            'scenarios': simulation_results,
            'num_scenarios': len(simulation_results),
            'total_requested': num_scenarios
        }
    except Exception as e:
        print(f"Error during Monte Carlo candles simulation: {e}")
        raise


