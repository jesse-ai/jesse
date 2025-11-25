from typing import List, Dict, Optional, Tuple, Any, TypedDict
import ray
from multiprocessing import cpu_count
import numpy as np
import os
from datetime import datetime
import jesse.helpers as jh
from jesse.research import backtest

from .common import (
    DEFAULT_CPU_USAGE_RATIO,
    MIN_CPU_CORES,
    CONFIDENCE_PERCENTILES,
    ALPHA_5_PERCENT,
    ALPHA_1_PERCENT,
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
            f"Scenario {scenario_index} failed with {error_type}: {error_msg}\n"
            f"{full_traceback}"
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
    progress_callback = None,
    result_callback = None,
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
            cpu_cores, ray_started_here, progress_callback, result_callback
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


def _calculate_confidence_intervals_candles(original_result: dict, simulation_results: list) -> dict:
    if not simulation_results:
        return {'error': 'No simulation results to analyze'}

    # Collect metrics from simulation results (candles scenarios return full backtest results)
    metrics = {
        'net_profit_percentage': [],
        'max_drawdown': [],
        'sharpe_ratio': [],
        'win_rate': [],
        'total': [],
        'annual_return': [],
        'calmar_ratio': []
    }

    for result in simulation_results:
        if 'metrics' in result:
            scenario_metrics = result['metrics']
            for key in metrics.keys():
                if key in scenario_metrics and isinstance(scenario_metrics[key], (int, float)):
                    metrics[key].append(scenario_metrics[key])

    original_metrics = original_result.get('metrics', {}) if original_result else {}
    confidence_analysis: Dict[str, Any] = {}

    for metric_name, values in metrics.items():
        if not values:
            continue
        values_array = np.array(values)

        # For candles, metrics are already in percentage format (like original backtest)
        # But for dashboard consistency, we keep them as percentages in confidence analysis
        original_value = original_metrics.get(metric_name, 0)

        percentiles = {
            '5th': np.percentile(values_array, 5),
            '25th': np.percentile(values_array, 25),
            '50th': np.percentile(values_array, 50),
            '75th': np.percentile(values_array, 75),
            '95th': np.percentile(values_array, 95)
        }

        ci_95 = {
            'lower': np.percentile(values_array, CONFIDENCE_PERCENTILES['extreme_low']),
            'upper': np.percentile(values_array, CONFIDENCE_PERCENTILES['extreme_high'])
        }
        ci_90 = {
            'lower': np.percentile(values_array, CONFIDENCE_PERCENTILES['low']),
            'upper': np.percentile(values_array, CONFIDENCE_PERCENTILES['high'])
        }

        # For max_drawdown, p_value logic is reversed (lower values are better)
        if metric_name == 'max_drawdown':
            p_value = np.sum(values_array <= original_value) / len(values_array)
        else:
            p_value = np.sum(values_array >= original_value) / len(values_array)

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

    summary = {
        'num_simulations': len(simulation_results),
        'significant_metrics_5pct': sum(1 for m in confidence_analysis.values() if m.get('is_significant_5pct', False)),
        'significant_metrics_1pct': sum(1 for m in confidence_analysis.values() if m.get('is_significant_1pct', False)),
        'total_metrics': len(confidence_analysis)
    }

    return {
        'summary': summary,
        'metrics': confidence_analysis,
        'interpretation': _generate_interpretation_candles(confidence_analysis)
    }


def _generate_interpretation_candles(confidence_analysis: dict) -> dict:
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

        if metric_name == 'max_drawdown':
            # For max_drawdown, lower percentiles are better
            if original <= percentiles['5th']:
                rank = "top 5% (lowest drawdowns)"
            elif original <= percentiles['25th']:
                rank = "top 25% (low drawdowns)"
            elif original <= percentiles['50th']:
                rank = "above median"
            elif original <= percentiles['75th']:
                rank = "below median"
            else:
                rank = "bottom 25% (high drawdowns)"
        else:
            # For other metrics, higher percentiles are better
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
        'overall': f"Strategy shows {sum(1 for i in interpretations if 'significant' in i['significance'])} out of {len(interpretations)} metrics being statistically significant."
    }


def _run_monte_carlo_candles_simulation(
    config: dict, routes: List[Dict[str, str]], data_routes: List[Dict[str, str]],
    candles: dict, warmup_candles: dict, hyperparameters: dict,
    fast_mode: bool, num_scenarios: int, progress_bar: bool,
    candles_pipeline_class, candles_pipeline_kwargs: dict, cpu_cores: int, started_ray_here: bool, progress_callback=None, result_callback=None
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
        results = _process_scenario_results(scenario_refs, pbar, progress_callback, result_callback)
        if pbar:
            pbar.close()
        valid_results, filtered_count = _filter_valid_results(results)
        _log_monte_carlo_candles_simulation_summary(valid_results, filtered_count, num_scenarios)

        # Separate original result (scenario_index == 0) from Monte Carlo simulations
        original_result = next((r for r in valid_results if r.get('scenario_index') == 0), None)
        simulation_results = [r for r in valid_results if r.get('scenario_index', -1) > 0]

        # Calculate confidence intervals
        confidence_analysis = _calculate_confidence_intervals_candles(original_result, simulation_results)

        return {
            'original': original_result,
            'scenarios': simulation_results,
            'confidence_analysis': confidence_analysis,
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
    if 'confidence_analysis' not in results:
        print("No confidence analysis available")
        return
    ca = results['confidence_analysis']
    summary = ca['summary']
    metrics = ca['metrics']
    print(f"\n📈 MONTE CARLO CANDLES (market-path robustness test)")
    print(f"   Valid scenarios: {summary['num_simulations']}")
    headers = ["Metric", "Original", "Worst 5%", "Median", "Best 5%"]
    rows = []
    for metric_name, a in metrics.items():
        if 'original' not in a:
            continue
        orig = a['original']
        percentiles = a.get('percentiles', {})
        p5 = percentiles.get('5th', 0)
        p50 = percentiles.get('50th', 0)
        p95 = percentiles.get('95th', 0)
        display_name = metric_name.replace('_', ' ').title()
        if 'percentage' in metric_name or 'return' in metric_name:
            orig_disp = f"{orig:.1f}%" if orig is not None else "—"
            p5_disp = f"{p5:.1f}%"; p50_disp = f"{p50:.1f}%"; p95_disp = f"{p95:.1f}%"
        elif metric_name == 'max_drawdown':
            display_name = "Max Drawdown (%)"
            orig_disp = f"-{abs(orig):.1f}%" if orig is not None else "—"
            p5_disp = f"-{abs(p5):.1f}%"; p50_disp = f"-{abs(p50):.1f}%"; p95_disp = f"-{abs(p95):.1f}%"
        elif metric_name in ['sharpe_ratio', 'calmar_ratio']:
            orig_disp = f"{orig:.2f}" if orig is not None else "—"
            p5_disp = f"{p5:.2f}"; p50_disp = f"{p50:.2f}"; p95_disp = f"{p95:.2f}"
        elif metric_name == 'win_rate':
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
    import matplotlib
    matplotlib.use('Agg')  # Use non-interactive backend
    from matplotlib import pyplot as plt
    
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


