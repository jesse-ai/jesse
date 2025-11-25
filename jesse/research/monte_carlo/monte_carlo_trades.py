from typing import List, Dict, Optional, Tuple, Any, TypedDict
import ray
from multiprocessing import cpu_count
import numpy as np
import random
import os
from datetime import datetime
import jesse.helpers as jh
from jesse.research import backtest

from .common import (
    DEFAULT_CPU_USAGE_RATIO,
    MIN_CPU_CORES,
    BASE_RANDOM_SEED,
    CONFIDENCE_PERCENTILES,
    ALPHA_5_PERCENT,
    ALPHA_1_PERCENT,
    ANNUALIZATION_FACTOR,
    MAX_DRAWDOWN_LIMIT,
    _setup_progress_bar,
    _process_scenario_results,
)

# ============================================================================
# Typed return structures for clearer docs and IDE support
# ============================================================================
class EquityCurvePoint(TypedDict):
    time: int
    value: float

class EquityCurveSeries(TypedDict):
    name: str  # 'Portfolio'
    data: List[EquityCurvePoint]

class MonteCarloTradeScenarioResult(TypedDict, total=False):
    # Metrics reconstructed from shuffled trades
    total_return: float
    final_value: float
    max_drawdown: float
    volatility: float
    sharpe_ratio: float
    calmar_ratio: float
    starting_balance: float
    # Added by ray_run_scenario_monte_carlo
    trades: List[Dict[str, Any]]
    equity_curve: List[EquityCurveSeries]

class ConfidenceIntervalBounds(TypedDict):
    lower: float
    upper: float

class ConfidenceIntervals(TypedDict):
    _90: ConfidenceIntervalBounds  # stored as '90%'
    _95: ConfidenceIntervalBounds  # stored as '95%'

class MetricPercentiles(TypedDict):
    _5th: float  # stored as '5th'
    _25th: float  # stored as '25th'
    _50th: float  # stored as '50th'
    _75th: float  # stored as '75th'
    _95th: float  # stored as '95th'

class SimulationAggregate(TypedDict):
    mean: float
    std: float
    min: float
    max: float
    count: int

class ConfidenceMetricAnalysis(TypedDict):
    original: float
    simulations: SimulationAggregate
    percentiles: Dict[str, float]
    confidence_intervals: Dict[str, ConfidenceIntervalBounds]
    p_value: float
    is_significant_5pct: bool
    is_significant_1pct: bool

class ConfidenceAnalysis(TypedDict):
    summary: Dict[str, int]
    metrics: Dict[str, ConfidenceMetricAnalysis]
    interpretation: Dict[str, Any]

class MonteCarloTradesReturn(TypedDict):
    original: Dict[str, Any]
    scenarios: List[MonteCarloTradeScenarioResult]
    confidence_analysis: ConfidenceAnalysis
    num_scenarios: int
    total_requested: int


@ray.remote
def _ray_run_scenario_monte_carlo(
    original_trades: list,
    original_equity_curve: list,
    starting_balance: float,
    scenario_index: int,
    seed: Optional[int] = None
) -> Dict[str, Any]:
    try:
        if seed is not None:
            scenario_seed = seed + scenario_index
            random.seed(scenario_seed)
            np.random.seed(scenario_seed)
        shuffled_trades = original_trades.copy()
        random.shuffle(shuffled_trades)
        equity_curve = _reconstruct_equity_curve_from_trades(
            shuffled_trades, original_equity_curve, starting_balance
        )
        result = _calculate_metrics_from_equity_curve(equity_curve, starting_balance)
        result['trades'] = shuffled_trades
        result['equity_curve'] = equity_curve
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


def monte_carlo_trades(
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
    progress_callback = None,
    result_callback = None,
) -> MonteCarloTradesReturn:
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
        return _run_monte_carlo_simulation(
            config, routes, data_routes, candles, warmup_candles,
            benchmark, hyperparameters, fast_mode, num_scenarios, progress_bar,
            cpu_cores, ray_started_here, progress_callback, result_callback
        )
    except Exception as e:
        jh.debug(f"Error during Monte Carlo simulation: {e}")
        raise
    finally:
        if ray_started_here and ray.is_initialized():
            ray.shutdown()


def _run_monte_carlo_simulation(
    config: dict, routes: List[Dict[str, str]], data_routes: List[Dict[str, str]],
    candles: dict, warmup_candles: dict, benchmark: bool, hyperparameters: dict, fast_mode: bool,
    num_scenarios: int, progress_bar: bool, cpu_cores: int, started_ray_here: bool, progress_callback=None, result_callback=None
) -> dict:
    try:
        original_result = _run_original_backtest(
            config, routes, data_routes, candles, warmup_candles,
            hyperparameters, fast_mode, benchmark
        )
        original_trades, original_equity_curve, starting_balance = _extract_trade_data(
            original_result, config
        )
        pbar = _setup_progress_bar(progress_bar, num_scenarios, "Monte Carlo Scenarios")
        trades_ref = ray.put(original_trades)
        equity_curve_ref = ray.put(original_equity_curve)
        scenario_refs = _launch_monte_carlo_scenarios(
            num_scenarios, trades_ref, equity_curve_ref, starting_balance
        )
        results = _process_scenario_results(scenario_refs, pbar, progress_callback, result_callback)
        if pbar:
            pbar.close()
        print(f"Completed {len(results)} Monte Carlo scenarios out of {num_scenarios} requested")
        confidence_analysis = _calculate_confidence_intervals(original_result, results)
        return {
            'original': original_result,
            'scenarios': results,
            'confidence_analysis': confidence_analysis,
            'num_scenarios': len(results),
            'total_requested': num_scenarios
        }
    except Exception as e:
        print(f"Error during Monte Carlo simulation: {e}")
        raise


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
    )


def _extract_trade_data(original_result: dict, config: dict) -> Tuple[list, list, float]:
    if 'trades' not in original_result:
        available_keys = list(original_result.keys())
        print(f"Available keys in backtest result: {available_keys}")
        raise ValueError("No 'trades' key found in backtest result. Cannot perform trade-shuffling Monte Carlo.")
    trades_list = original_result['trades']
    if not trades_list:
        _diagnose_empty_trades(original_result)
        raise ValueError("No trades found in original backtest. Cannot perform trade-shuffling Monte Carlo.")
    original_equity_curve = original_result['equity_curve']
    starting_balance = config.get('starting_balance', 10000)
    return trades_list, original_equity_curve, starting_balance


def _diagnose_empty_trades(original_result: dict) -> None:
    print("Trades list is empty. This could happen if:")
    print("1. The strategy didn't generate any trades")
    print("2. The time period was too short")
    print("3. The strategy conditions were never met")
    if 'metrics' in original_result:
        total_trades = original_result['metrics'].get('total', 0)
        print(f"   Metrics shows total trades: {total_trades}")


def _launch_monte_carlo_scenarios(
    num_scenarios: int,
    trades_ref: Any,
    equity_curve_ref: Any,
    starting_balance: float
) -> List[Any]:
    scenario_refs: List[Any] = []
    for i in range(num_scenarios):
        ref = _ray_run_scenario_monte_carlo.remote(
            original_trades=trades_ref,
            original_equity_curve=equity_curve_ref,
            starting_balance=starting_balance,
            scenario_index=i,
            seed=BASE_RANDOM_SEED
        )
        scenario_refs.append(ref)
    return scenario_refs


def _reconstruct_equity_curve_from_trades(shuffled_trades: list, original_equity_curve: list, starting_balance: float) -> list:
    if not original_equity_curve or not original_equity_curve[0].get('data'):
        raise ValueError("Invalid original equity curve format")
    original_data = original_equity_curve[0]['data']
    time_points = [item.get('time', item.get('timestamp', 0)) for item in original_data]
    new_equity_curve = [{
        'name': 'Portfolio',
        'data': []
    }]
    current_balance = starting_balance
    trade_index = 0
    total_trades = len(shuffled_trades)
    total_time_points = len(time_points)
    trades_per_point = total_trades / total_time_points if total_time_points > 0 else 1
    for i, timestamp in enumerate(time_points):
        target_trades_completed = int((i + 1) * trades_per_point)
        trades_to_add = target_trades_completed - trade_index
        for _ in range(trades_to_add):
            if trade_index < total_trades:
                current_balance += shuffled_trades[trade_index]['PNL']
                trade_index += 1
        new_equity_curve[0]['data'].append({
            'time': timestamp,
            'value': current_balance
        })
    return new_equity_curve


def _calculate_metrics_from_equity_curve(equity_curve: list, starting_balance: float) -> dict:
    if not equity_curve or not equity_curve[0].get('data'):
        return {'error': 'Invalid equity curve'}
    data = equity_curve[0]['data']
    values = [item['value'] for item in data]

    if not values:
        return {'error': 'No data in equity curve'}
    final_value = values[-1]
    total_return = ((final_value - starting_balance) / starting_balance) * 100
    max_drawdown = _calculate_max_drawdown(values)
    volatility, sharpe_ratio = _calculate_volatility_metrics(values)
    calmar_ratio = total_return / abs(max_drawdown) if max_drawdown < 0 else 0
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
    Calculates the maximum drawdown from equity curve values (prices)
    Same approach as metrics.py: (prices / prices.expanding(min_periods=0).max()).min() - 1
    """
    if not values:
        return 0.0

    # Find running maximum
    running_max = values[0]
    max_drawdown = 0.0

    for price in values:
        running_max = max(running_max, price)
        drawdown = price / running_max - 1
        max_drawdown = min(max_drawdown, drawdown)

    return max_drawdown * 100


def _calculate_volatility_metrics(values: List[float]) -> Tuple[float, float]:
    if len(values) <= 1:
        return 0.0, 0.0
    returns: List[float] = []
    for i in range(1, len(values)):
        if values[i-1] != 0:
            daily_return = (values[i] - values[i-1]) / values[i-1]
            returns.append(daily_return)
    if not returns:
        return 0.0, 0.0
    daily_std = np.std(returns)
    annualized_volatility = daily_std * np.sqrt(ANNUALIZATION_FACTOR)
    avg_daily_return = np.mean(returns)
    annualized_return = avg_daily_return * ANNUALIZATION_FACTOR
    sharpe_ratio = annualized_return / annualized_volatility if annualized_volatility > 0 else 0
    return annualized_volatility, sharpe_ratio


def _calculate_confidence_intervals(original_result: dict, simulation_results: list) -> dict:
    if not simulation_results:
        return {'error': 'No simulation results to analyze'}
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
    original_metrics = original_result.get('metrics', {})

    confidence_analysis: Dict[str, Any] = {}
    for metric_name, values in metrics.items():
        if not values:
            continue
        values_array = np.array(values)
        
        # Normalize original metrics to match Monte Carlo scenario format (decimal, not percentage)
        if metric_name == 'total_return':
            # Calculate from net_profit_percentage (which is in percentage form)
            net_profit_pct = original_metrics.get('net_profit_percentage', 0)
            original_value = net_profit_pct  # Convert to decimal
        elif metric_name == 'max_drawdown':
            # Original backtest returns max_drawdown already multiplied by 100
            max_dd = original_metrics.get('max_drawdown', 0)
            original_value = max_dd  # Convert to decimal
        else:
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
        if metric_name in ['total_return', 'sharpe_ratio', 'calmar_ratio']:
            p_value = np.sum(values_array >= original_value) / len(values_array)
        else:
            p_value = np.sum(values_array <= original_value) / len(values_array)
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
        'interpretation': _generate_interpretation(confidence_analysis)
    }


def _generate_interpretation(confidence_analysis: dict) -> dict:
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


def print_monte_carlo_trades_summary(results: dict) -> None:
    """Print a summary table for Monte Carlo trades scenarios.

    Args:
        results: The full results dict returned by monte_carlo_trades().
    """
    if 'confidence_analysis' not in results:
        print("No confidence analysis available")
        return
    ca = results['confidence_analysis']
    summary = ca['summary']
    metrics = ca['metrics']
    print(f"\n🔀 MONTE CARLO TRADES (trade-order shuffle test)")
    print(f"   Simulations: {summary['num_simulations']}")
    headers = ["Metric", "Original", "Worst 5%", "Median", "Best 5%"]
    rows = []
    for metric_name, a in metrics.items():
        if 'original' not in a:
            continue
        orig = a['original']
        sim = a.get('simulations', {})
        percentiles = a.get('percentiles', {})
        invariant = (sim.get('std', 0) is not None and sim.get('std', 0) < 1e-12)
        if invariant:
            continue
        p5 = percentiles.get('5th', 0)
        p50 = percentiles.get('50th', 0)
        p95 = percentiles.get('95th', 0)
        display_name = metric_name.replace('_', ' ').title()
        if display_name == "Total Return":
            display_name = "Return (%)"
            orig_display = f"{orig*100:.1f}%"; p5_disp = f"{p5*100:.1f}%"; p50_disp = f"{p50*100:.1f}%"; p95_disp = f"{p95*100:.1f}%"
        elif display_name == "Max Drawdown":
            display_name = "Max Drawdown (%)"
            orig_display = f"{(orig):.1f}%"
            p5_disp = f"{(p5):.1f}%"; p50_disp = f"{(p50):.1f}%"; p95_disp = f"{(p95):.1f}%"
        elif display_name in ["Sharpe Ratio", "Calmar Ratio"]:
            orig_display = f"{orig:.2f}"; p5_disp = f"{p5:.2f}"; p50_disp = f"{p50:.2f}"; p95_disp = f"{p95:.2f}"
        else:
            orig_display = f"{orig:.2f}" if isinstance(orig, (int, float)) else str(orig)
            p5_disp = f"{p5:.2f}"; p50_disp = f"{p50:.2f}"; p95_disp = f"{p95:.2f}"
        rows.append([display_name, orig_display, p5_disp, p50_disp, p95_disp])
    if rows:
        col_widths = [max(len(str(x)) for x in [h] + [r[i] for r in rows]) for i, h in enumerate(headers)]
        line = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
        sep = "-+-".join("-" * w for w in col_widths)
        print("   " + line); print("   " + sep)
        for r in rows:
            print("   " + " | ".join(str(r[i]).ljust(col_widths[i]) for i in range(len(headers))))
        print(f"\n   📊 Interpretation:")
        print(f"   • This tests whether trade timing affects performance")
    else:
        print("No metrics rows to display")


def plot_monte_carlo_trades_chart(results: dict, charts_folder: str = None) -> None:
    """Plot equity curves from Monte Carlo trades results.

    Args:
        results: The full results dict returned by monte_carlo_trades().
        charts_folder: Optional folder to save charts in.
    """
    import matplotlib
    matplotlib.use('Agg')  # Use non-interactive backend
    from matplotlib import pyplot as plt
    
    if 'scenarios' not in results or not results['scenarios']:
        print("No trade shuffle scenarios to plot")
        return
    plt.figure(figsize=(12, 8))
    for i, scenario in enumerate(results['scenarios'][:50]):  # Limit to 50 for visibility
        if 'equity_curve' in scenario and scenario['equity_curve']:
            values = [item['value'] for item in scenario['equity_curve'][0]['data']]
            plt.plot(values, color="cornflowerblue", alpha=0.5, linewidth=0.8)
    if 'original' in results and 'equity_curve' in results['original']:
        original_values = [item['value'] for item in results['original']['equity_curve'][0]['data']]
        plt.plot(original_values, color="green", linewidth=2, label="Original Strategy")
    plt.title("Monte Carlo Trades - Equity Curve (Shuffled Order)")
    plt.xlabel("Time"); plt.ylabel("Portfolio Value"); plt.legend(); plt.grid(True, alpha=0.3); plt.tight_layout()
    if charts_folder is None:
        charts_folder = _create_charts_folder()
    filename = _get_timestamped_filename("monte_carlo_trades_chart.png")
    chart_path = os.path.join(charts_folder, filename)
    plt.savefig(chart_path, dpi=150, bbox_inches='tight'); plt.close()
    print(f"   💾 Trades chart saved: {chart_path}")


