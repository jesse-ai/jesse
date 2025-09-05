from typing import List, Dict, Optional, Tuple, Any, TypedDict
import ray
from multiprocessing import cpu_count
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
from matplotlib import pyplot as plt
import os
from datetime import datetime
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
def _ray_run_scenario_monte_carlo_candles(
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
        ref = _ray_run_scenario_monte_carlo_candles.remote(
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


def _get_timestamped_filename(base_name: str) -> str:
    """Generate a timestamped filename."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name, ext = os.path.splitext(base_name)
    return f"{name}_{timestamp}{ext}"


def _create_charts_folder():
    """Create a charts folder for all outputs."""
    folder_path = os.path.abspath("charts")
    os.makedirs(folder_path, exist_ok=True)
    return folder_path


def print_monte_carlo_candles_summary(results: dict) -> None:
    """Print a robustness table for Monte Carlo candles scenarios.

    Args:
        results: The full results dict returned by monte_carlo_candles(). Must contain 'original' and 'scenarios'.
    """
    if not results or 'scenarios' not in results or not results['scenarios']:
        print("❌ No simulation results to summarize")
        return
    original_result = results.get('original')
    simulation_results = results.get('scenarios', [])
    valid_simulations = [r for r in simulation_results if r.get('metrics')]
    if not valid_simulations:
        print("❌ No valid simulation results with metrics to summarize")
        return
    important_metrics = [
        'net_profit_percentage', 'max_drawdown', 'sharpe_ratio', 'win_rate', 
        'total', 'annual_return', 'calmar_ratio', 'expectancy_percentage'
    ]
    if original_result and original_result.get('metrics'):
        available_metrics = list(original_result['metrics'].keys())
    else:
        for r in valid_simulations:
            available_metrics = list(r['metrics'].keys())
            break
        else:
            print("❌ No metrics found in simulation results")
            return
    metric_keys = [m for m in important_metrics if m in available_metrics]
    values_by_metric: dict[str, list[float]] = {k: [] for k in metric_keys}
    for r in valid_simulations:
        m = r.get('metrics', {})
        for k in metric_keys:
            v = m.get(k)
            if isinstance(v, (int, float)) and np.isfinite(v):
                values_by_metric[k].append(float(v))
    print(f"\n📈 MONTE CARLO CANDLES (market-path robustness test)")
    print(f"   Valid scenarios: {len(valid_simulations)}")
    headers = ["Metric", "Original", "Worst 5%", "Median", "Best 5%"]
    rows = []
    for k in metric_keys:
        vals = values_by_metric.get(k, [])
        if len(vals) == 0:
            continue
        arr = np.array(vals, dtype=float)
        p5 = np.percentile(arr, 5)
        p50 = np.percentile(arr, 50)
        p95 = np.percentile(arr, 95)
        orig = None
        if original_result and original_result.get('metrics'):
            o = original_result['metrics'].get(k)
            if isinstance(o, (int, float)) and np.isfinite(o):
                orig = float(o)
        display_name = k.replace('_', ' ').title()
        if 'percentage' in k or 'return' in k:
            orig_disp = f"{orig:.1f}%" if orig is not None else "—"
            p5_disp = f"{p5:.1f}%"; p50_disp = f"{p50:.1f}%"; p95_disp = f"{p95:.1f}%"
        elif k == 'max_drawdown':
            display_name = "Max Drawdown (%)"
            orig_disp = f"-{abs(orig):.1f}%" if orig is not None else "—"
            p5_disp = f"-{abs(p5):.1f}%"; p50_disp = f"-{abs(p50):.1f}%"; p95_disp = f"-{abs(p95):.1f}%"
        elif k in ['sharpe_ratio', 'calmar_ratio']:
            orig_disp = f"{orig:.2f}" if orig is not None else "—"
            p5_disp = f"{p5:.2f}"; p50_disp = f"{p50:.2f}"; p95_disp = f"{p95:.2f}"
        elif k == 'win_rate':
            display_name = "Win Rate (%)"
            orig_disp = f"{orig*100:.1f}%" if orig is not None else "—"
            p5_disp = f"{p5*100:.1f}%"; p50_disp = f"{p50*100:.1f}%"; p95_disp = f"{p95*100:.1f}%"
        else:
            orig_disp = f"{orig:.1f}" if orig is not None else "—"
            p5_disp = f"{p5:.1f}"; p50_disp = f"{p50:.1f}"; p95_disp = f"{p95:.1f}"
        rows.append([display_name, orig_disp, p5_disp, p50_disp, p95_disp])
    if not rows:
        print("❌ No numeric metrics to summarize")
        return
    col_widths = [max(len(str(x)) for x in [h] + [r[i] for r in rows]) for i, h in enumerate(headers)]
    line = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    sep = "-+-".join("-" * w for w in col_widths)
    print("   " + line); print("   " + sep)
    for r in rows:
        print("   " + " | ".join(str(r[i]).ljust(col_widths[i]) for i in range(len(headers))))
    print(f"\n   📊 Interpretation:")
    print(f"   • This tests how your strategy performs across different market conditions under resampled candles")


def plot_monte_carlo_candles_chart(results: dict, charts_folder: str = None) -> None:
    """Plot equity curves from Monte Carlo candles results.

    Args:
        results: The full results dict returned by monte_carlo_candles(). Must contain 'original' and 'scenarios'.
        charts_folder: Optional folder to save charts in.
    """
    if not results or 'scenarios' not in results or not results['scenarios']:
        print("No simulation results to plot")
        return
    original_result = results.get('original')
    simulation_results = results.get('scenarios', [])
    print(f"Number of Monte Carlo candles scenarios found: {len(simulation_results)}")
    for simulation in simulation_results:
        if "equity_curve" in simulation and simulation["equity_curve"]:
            for equity_curve in simulation["equity_curve"]:
                if equity_curve["name"] == "Portfolio":
                    values = [item["value"] for item in equity_curve["data"]]
                    plt.plot(values, color="cornflowerblue", alpha=0.5, linewidth=0.8)
    if original_result and "equity_curve" in original_result and original_result["equity_curve"]:
        for equity_curve in original_result["equity_curve"]:
            if equity_curve["name"] == "Portfolio":
                values = [item["value"] for item in equity_curve["data"]]
                plt.plot(values, color="green", linewidth=2, label="Original Strategy")
    plt.title("Monte Carlo Candles - Equity Curve")
    plt.legend(); plt.tight_layout()
    if charts_folder is None:
        charts_folder = _create_charts_folder()
    filename = _get_timestamped_filename("monte_carlo_candles_chart.png")
    chart_path = os.path.join(charts_folder, filename)
    plt.savefig(chart_path, dpi=150, bbox_inches='tight'); plt.close()
    print(f"Saved Monte Carlo candles chart to: {chart_path}")


