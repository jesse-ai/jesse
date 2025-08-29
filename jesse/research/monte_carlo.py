from typing import List, Dict, Literal
import ray
from multiprocessing import cpu_count
import numpy as np
import random
import jesse.helpers as jh
from jesse.research import backtest

@ray.remote
def ray_run_scenario_candles(
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
):
    """Ray remote function to run a single Monte Carlo scenario"""
    try:
        # Determine benchmark and pipeline behavior per scenario
        is_benchmark_scenario = benchmark and scenario_index == 0
        effective_with_candles_pipeline = candles_pipeline_class is not None and (not is_benchmark_scenario)

        result = backtest(
            config=config,
            routes=routes,
            data_routes=data_routes,
            candles=candles,
            warmup_candles=warmup_candles,
            generate_equity_curve=True,
            hyperparameters=hyperparameters,
            fast_mode=fast_mode,
            benchmark=is_benchmark_scenario,
            candles_pipeline_class=candles_pipeline_class if effective_with_candles_pipeline else None,
            candles_pipeline_kwargs=candles_pipeline_kwargs if effective_with_candles_pipeline else None
        )
        
        # Simply log scenarios with missing equity curve
        if 'equity_curve' not in result or result['equity_curve'] is None:
            # The logs will be collected but not displayed directly
            return {'result': result, 'log': f"Info: Scenario {scenario_index} missing equity_curve - this will be filtered out"}
                
        return {'result': result, 'log': None}
    except Exception as e:
        # Return the error instead of logging directly
        error_msg = f"Ray scenario {scenario_index} failed with exception: {str(e)}"
        return {'result': None, 'log': error_msg, 'error': True}

@ray.remote
def ray_run_scenario_trades(
    original_trades: list,
    original_equity_curve: list,
    starting_balance: float,
    scenario_index: int,
    seed: int = None
):
    """Ray remote function to run a single trade-shuffling Monte Carlo scenario"""
    try:
        # Set seed for reproducibility if provided
        if seed is not None:
            random.seed(seed + scenario_index)
            np.random.seed(seed + scenario_index)
        
        # Shuffle the trades
        shuffled_trades = original_trades.copy()
        random.shuffle(shuffled_trades)
        
        # Reconstruct equity curve from shuffled trades
        equity_curve = _reconstruct_equity_curve_from_trades(shuffled_trades, original_equity_curve, starting_balance)
        
        # Calculate metrics from shuffled equity curve
        result = _calculate_metrics_from_equity_curve(equity_curve, starting_balance)
        result['trades'] = shuffled_trades
        result['equity_curve'] = equity_curve
        
        return {'result': result, 'log': None}
    except Exception as e:
        error_msg = f"Ray trade scenario {scenario_index} failed with exception: {str(e)}"
        return {'result': None, 'log': error_msg, 'error': True}

def monte_carlo(
    config: dict,
    routes: List[Dict[str, str]],
    data_routes: List[Dict[str, str]],
    candles: dict,
    warmup_candles: dict = None,
    benchmark: bool = False,
    hyperparameters: dict = None,
    fast_mode: bool = True,
    num_scenarios: int = 1000,
    progress_bar: bool = False,
    simulation_type: Literal["candles", "trades"] = "candles",
    candles_pipeline_class = None,
    candles_pipeline_kwargs: dict = None,
    cpu_cores: int = None,
) -> dict:
    # Validate simulation type
    if simulation_type not in ["candles", "trades"]:
        raise ValueError("simulation_type must be either 'candles' or 'trades'")
    
    # For trades simulation, we need candles_pipeline_class to be None
    if simulation_type == "trades" and candles_pipeline_class is not None:
        raise ValueError("candles_pipeline_class must be None for trades simulation type")
    
    # Determine the number of CPU cores to use
    if cpu_cores is None:
        available_cores = cpu_count()
        # Use 80% of available cores by default, but at least 1
        cpu_cores = max(1, int(available_cores * 0.8))
    else:
        # Make sure cpu_cores is at least 1 and not more than available
        available_cores = cpu_count()
        cpu_cores = max(1, min(cpu_cores, available_cores))

    # Initialize Ray if not already initialized
    started_ray_here = False
    if not ray.is_initialized():
        try:
            ray.init(num_cpus=cpu_cores, ignore_reinit_error=True)
            print(f"Successfully started Monte Carlo simulation with {cpu_cores} CPU cores")
            started_ray_here = True
        except Exception as e:
            raise RuntimeError(f"Error initializing Ray: {e}")

    try:
        if simulation_type == "candles":
            return _run_candles_simulation(
                config, routes, data_routes, candles, warmup_candles, 
                benchmark, hyperparameters, fast_mode, num_scenarios, 
                progress_bar, candles_pipeline_class, candles_pipeline_kwargs, 
                cpu_cores, started_ray_here
            )
        else:  # simulation_type == "trades"
            return _run_trades_simulation(
                config, routes, data_routes, candles, warmup_candles,
                benchmark, hyperparameters, fast_mode, num_scenarios, progress_bar,
                cpu_cores, started_ray_here
            )
    
    except Exception as e:
        print(f"Error during Monte Carlo simulation: {e}")
        raise
    
    finally:
        # Shutdown Ray only if this function initialized it
        if started_ray_here and ray.is_initialized():
            ray.shutdown()

def _run_candles_simulation(
    config: dict, routes: List[Dict[str, str]], data_routes: List[Dict[str, str]], 
    candles: dict, warmup_candles: dict, benchmark: bool, hyperparameters: dict, 
    fast_mode: bool, num_scenarios: int, progress_bar: bool, 
    candles_pipeline_class, candles_pipeline_kwargs: dict, cpu_cores: int, started_ray_here: bool
) -> dict:
    """Run candles-based Monte Carlo simulation"""
    try:
        # Initialize progress bar if requested
        if progress_bar:
            if jh.is_notebook():
                from tqdm.notebook import tqdm
            else:
                from tqdm import tqdm
            pbar = tqdm(total=num_scenarios, desc="Monte Carlo Scenarios (Candles)")
        else:
            pbar = None

        # Put large, shared objects in Ray's object store
        config_ref = ray.put(config)
        routes_ref = ray.put(routes)
        data_routes_ref = ray.put(data_routes)
        candles_ref = ray.put(candles)
        warmup_candles_ref = ray.put(warmup_candles)
        hyperparameters_ref = ray.put(hyperparameters)

        # Launch all scenarios in parallel (including single-scenario cases)
        refs = []
        for i in range(num_scenarios):
            ref = ray_run_scenario_candles.remote(
                config=config_ref,
                routes=routes_ref,
                data_routes=data_routes_ref,
                candles=candles_ref,
                warmup_candles=warmup_candles_ref,
                hyperparameters=hyperparameters_ref,
                fast_mode=fast_mode,
                benchmark=benchmark,
                scenario_index=i,
                candles_pipeline_class=candles_pipeline_class,
                candles_pipeline_kwargs=candles_pipeline_kwargs
            )
            refs.append(ref)

        # Process results as they complete
        results = []
        while refs:
            # Wait for any task to complete (with timeout for responsiveness)
            done_refs, refs = ray.wait(refs, num_returns=1, timeout=0.5)
            
            if done_refs:
                for ref in done_refs:
                    # Get and append result
                    try:
                        response = ray.get(ref)
                        
                        # Handle the response structure (result and log)
                        if isinstance(response, dict) and 'result' in response:
                            # Add the result if it exists
                            if response['result'] is not None:
                                results.append(response['result'])
                            
                            # Print log messages in a way that doesn't interfere with the progress bar
                            if response.get('log') and pbar:
                                if jh.is_notebook():
                                    print(response['log'])
                                else:
                                    tqdm.write(response['log'])
                            
                            # Handle errors
                            if response.get('error', False):
                                print(f"Error in scenario: {response.get('log')}")
                        else:
                            # Handle old format for backward compatibility
                            results.append(response)
                    except Exception as e:
                        if pbar:
                            if jh.is_notebook():
                                print(f"Error processing scenario result: {str(e)}")
                            else:
                                tqdm.write(f"Error processing scenario result: {str(e)}")
                        else:
                            print(f"Error processing scenario result: {str(e)}")
                    
                    # Update progress bar
                    if pbar:
                        pbar.update(1)
        
        if pbar:
            pbar.close()
        
        # Filter out results with missing equity curve
        valid_results = [r for r in results if 'equity_curve' in r and r['equity_curve'] is not None]
        filtered_count = len(results) - len(valid_results)
        
        if filtered_count > 0:
            print(f"Filtered out {filtered_count} scenarios with missing equity curves")
        
        print(f"Returned {len(valid_results)} valid scenarios out of {num_scenarios} total")
        
        return {
            'type': 'candles',
            'scenarios': valid_results,
            'num_scenarios': len(valid_results),
            'total_requested': num_scenarios
        }
    
    except Exception as e:
        print(f"Error during candles Monte Carlo simulation: {e}")
        raise

def _run_trades_simulation(
    config: dict, routes: List[Dict[str, str]], data_routes: List[Dict[str, str]], 
    candles: dict, warmup_candles: dict, benchmark: bool, hyperparameters: dict, fast_mode: bool, 
    num_scenarios: int, progress_bar: bool, cpu_cores: int, started_ray_here: bool
) -> dict:
    """Run trades-based Monte Carlo simulation"""
    try:
        print("Running original backtest to extract trades...")
        
        # Run original backtest to get trade history
        original_result = backtest(
            config=config,
            routes=routes,
            data_routes=data_routes,
            candles=candles,
            warmup_candles=warmup_candles,
            generate_equity_curve=True,
            hyperparameters=hyperparameters,
            fast_mode=fast_mode,
            benchmark=benchmark
            # No candles_pipeline_class means no pipeline for original data
        )
        
        # Check if trades are available
        if 'trades' not in original_result:
            print(f"Available keys in backtest result: {list(original_result.keys())}")
            raise ValueError("No 'trades' key found in backtest result. Cannot perform trade-shuffling Monte Carlo.")
        
        trades_list = original_result['trades']
        if not trades_list:
            print("Trades list is empty. This could happen if:")
            print("1. The strategy didn't generate any trades")
            print("2. The time period was too short")
            print("3. The strategy conditions were never met")
            if 'metrics' in original_result:
                total_trades = original_result['metrics'].get('total', 0)
                print(f"   Metrics shows total trades: {total_trades}")
            raise ValueError("No trades found in original backtest. Cannot perform trade-shuffling Monte Carlo.")
        
        print(f"Found {len(trades_list)} trades in original backtest")
        
        original_trades = original_result['trades']
        original_equity_curve = original_result['equity_curve']
        starting_balance = config.get('starting_balance', 10000)
        
        print(f"Found {len(original_trades)} trades in original backtest")
        
        # Initialize progress bar if requested
        if progress_bar:
            if jh.is_notebook():
                from tqdm.notebook import tqdm
            else:
                from tqdm import tqdm
            pbar = tqdm(total=num_scenarios, desc="Monte Carlo Scenarios (Trades)")
        else:
            pbar = None

        # Put shared objects in Ray's object store
        original_trades_ref = ray.put(original_trades)
        original_equity_curve_ref = ray.put(original_equity_curve)
        
        # Launch all scenarios in parallel
        refs = []
        for i in range(num_scenarios):
            ref = ray_run_scenario_trades.remote(
                original_trades=original_trades_ref,
                original_equity_curve=original_equity_curve_ref,
                starting_balance=starting_balance,
                scenario_index=i,
                seed=42  # Fixed seed for reproducibility
            )
            refs.append(ref)

        # Process results as they complete
        results = []
        while refs:
            # Wait for any task to complete (with timeout for responsiveness)
            done_refs, refs = ray.wait(refs, num_returns=1, timeout=0.5)
            
            if done_refs:
                for ref in done_refs:
                    try:
                        response = ray.get(ref)
                        
                        if isinstance(response, dict) and 'result' in response:
                            if response['result'] is not None:
                                results.append(response['result'])
                            
                            # Print log messages
                            if response.get('log') and pbar:
                                if jh.is_notebook():
                                    print(response['log'])
                                else:
                                    tqdm.write(response['log'])
                            
                            # Handle errors
                            if response.get('error', False):
                                print(f"Error in scenario: {response.get('log')}")
                    except Exception as e:
                        if pbar:
                            if jh.is_notebook():
                                print(f"Error processing scenario result: {str(e)}")
                            else:
                                tqdm.write(f"Error processing scenario result: {str(e)}")
                        else:
                            print(f"Error processing scenario result: {str(e)}")
                    
                    # Update progress bar
                    if pbar:
                        pbar.update(1)
        
        if pbar:
            pbar.close()

        print(f"Completed {len(results)} trade-shuffling scenarios out of {num_scenarios} requested")
        
        # Calculate confidence intervals and statistics
        confidence_analysis = _calculate_confidence_intervals(original_result, results)
        
        return {
            'type': 'trades',
            'original': original_result,
            'scenarios': results,
            'confidence_analysis': confidence_analysis,
            'num_scenarios': len(results),
            'total_requested': num_scenarios
        }
    
    except Exception as e:
        print(f"Error during trades Monte Carlo simulation: {e}")
        raise

def _reconstruct_equity_curve_from_trades(shuffled_trades: list, original_equity_curve: list, starting_balance: float) -> list:
    """Reconstruct equity curve from shuffled trades"""
    if not original_equity_curve or not original_equity_curve[0].get('data'):
        raise ValueError("Invalid original equity curve format")
    
    # Get the original time points from the equity curve
    original_data = original_equity_curve[0]['data']  # Assuming Portfolio curve is first
    time_points = [item.get('time', item.get('timestamp', 0)) for item in original_data]
    
    # Initialize new equity curve with same structure
    new_equity_curve = [{
        'name': 'Portfolio',
        'data': []
    }]
    
    # Sort trades by their original index to maintain some temporal distribution
    total_pnl = sum(trade['PNL'] for trade in shuffled_trades)
    
    # Create a simple linear distribution of trades across time
    current_balance = starting_balance
    trade_index = 0
    trades_per_point = len(shuffled_trades) / len(time_points) if time_points else 1
    
    for i, timestamp in enumerate(time_points):
        # Add trades for this time point
        trades_to_add = int((i + 1) * trades_per_point) - trade_index
        
        for _ in range(trades_to_add):
            if trade_index < len(shuffled_trades):
                current_balance += shuffled_trades[trade_index]['PNL']
                trade_index += 1
        
        new_equity_curve[0]['data'].append({
            'time': timestamp,
            'value': current_balance
        })
    
    return new_equity_curve

def _calculate_metrics_from_equity_curve(equity_curve: list, starting_balance: float) -> dict:
    """Calculate performance metrics from equity curve"""
    if not equity_curve or not equity_curve[0].get('data'):
        return {'error': 'Invalid equity curve'}
    
    data = equity_curve[0]['data']
    values = [item['value'] for item in data]
    
    if not values:
        return {'error': 'No data in equity curve'}
    
    # Calculate basic metrics
    final_value = values[-1]
    total_return = (final_value - starting_balance) / starting_balance
    
    # Calculate max drawdown
    peak = starting_balance
    max_drawdown = 0.0
    
    for value in values:
        if value > peak:
            peak = value
        drawdown = (peak - value) / peak if peak > 0 else 0
        max_drawdown = max(max_drawdown, drawdown)
    
    # Calculate volatility (annualized, assuming daily data)
    if len(values) > 1:
        returns = [(values[i] - values[i-1]) / values[i-1] for i in range(1, len(values)) if values[i-1] != 0]
        if returns:
            volatility = np.std(returns) * np.sqrt(252)  # Annualized
            avg_return = np.mean(returns)
            sharpe_ratio = (avg_return * 252) / volatility if volatility > 0 else 0
        else:
            volatility = 0
            sharpe_ratio = 0
    else:
        volatility = 0
        sharpe_ratio = 0
    
    return {
        'total_return': total_return,
        'final_value': final_value,
        'max_drawdown': max_drawdown,
        'volatility': volatility,
        'sharpe_ratio': sharpe_ratio,
        'starting_balance': starting_balance
    }

def _calculate_confidence_intervals(original_result: dict, simulation_results: list) -> dict:
    """Calculate confidence intervals and statistical analysis"""
    if not simulation_results:
        return {'error': 'No simulation results to analyze'}
    
    # Extract metrics from all simulations
    metrics = {
        'total_return': [],
        'final_value': [],
        'max_drawdown': [],
        'volatility': [],
        'sharpe_ratio': []
    }
    
    for result in simulation_results:
        for key in metrics.keys():
            if key in result and isinstance(result[key], (int, float)):
                metrics[key].append(result[key])
    
    # Calculate original metrics for comparison
    original_metrics = _calculate_metrics_from_equity_curve(
        original_result.get('equity_curve', []), 
        original_result.get('starting_balance', 10000)
    )
    
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
            'lower': np.percentile(values_array, 2.5),
            'upper': np.percentile(values_array, 97.5)
        }
        
        ci_90 = {
            'lower': np.percentile(values_array, 5),
            'upper': np.percentile(values_array, 95)
        }
        
        # Calculate p-value (probability of getting original result or better by chance)
        if metric_name in ['total_return', 'final_value', 'sharpe_ratio']:
            # Higher is better
            p_value = np.sum(values_array >= original_value) / len(values_array)
        else:
            # Lower is better (max_drawdown, volatility)
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
            'is_significant_5pct': p_value < 0.05,
            'is_significant_1pct': p_value < 0.01
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
