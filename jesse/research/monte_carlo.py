import functools
from typing import List, Dict
import ray
from multiprocessing import cpu_count
import jesse.helpers as jh
from jesse.research import backtest
import jesse.services.logger as logger

@ray.remote
def ray_run_scenario(
    config: dict,
    routes: List[Dict[str, str]],
    data_routes: List[Dict[str, str]],
    candles: dict,
    warmup_candles: dict,
    hyperparameters: dict,
    fast_mode: bool,
    benchmark: bool,
    scenario_index: int,
    with_candles_pipeline: bool
):
    """Ray remote function to run a single Monte Carlo scenario"""
    try:
        result = backtest(
            config=config,
            routes=routes,
            data_routes=data_routes,
            candles=candles,
            warmup_candles=warmup_candles,
            generate_equity_curve=True,
            hyperparameters=hyperparameters,
            fast_mode=fast_mode,
            benchmark=benchmark and scenario_index == 0,
            with_candles_pipeline=with_candles_pipeline and scenario_index != 0
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

def monte_carlo(
    config: dict,
    routes: List[Dict[str, str]],
    data_routes: List[Dict[str, str]],
    candles: dict,
    warmup_candles: dict = None,
    benchmark: bool = False,
    hyperparameters: dict = None,
    fast_mode: bool = True,
    scenarios: int = 1000,
    progress_bar: bool = False,
    with_candles_pipeline: bool = True,
    cpu_cores: int = None,
) -> list[dict]:
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
    if not ray.is_initialized():
        try:
            ray.init(num_cpus=cpu_cores, ignore_reinit_error=True)
            print(f"Successfully started Monte Carlo simulation with {cpu_cores} CPU cores")
        except Exception as e:
            print(f"Error initializing Ray: {e}. Falling back to sequential mode.")
            # Use sequential processing instead
            if progress_bar:
                if jh.is_notebook():
                    from tqdm.notebook import tqdm
                else:
                    from tqdm import tqdm
                pbar = tqdm(total=scenarios, desc="Monte Carlo Scenarios")
            else:
                pbar = None
                
            _backtest = functools.partial(
                backtest,
                config=config,
                routes=routes,
                data_routes=data_routes,
                candles=candles,
                warmup_candles=warmup_candles,
                generate_equity_curve=True,
                hyperparameters=hyperparameters,
                fast_mode=fast_mode,
                with_candles_pipeline=with_candles_pipeline
            )

            results = []
            for i in range(scenarios):
                result = _backtest(
                    benchmark=benchmark and i == 0, 
                    with_candles_pipeline=i != 0
                )
                results.append(result)
                if pbar:
                    pbar.update(1)
                    if 'equity_curve' not in result or result['equity_curve'] is None:
                        if jh.is_notebook():
                            print(f"Info: Scenario {i} missing equity_curve - this will be filtered out")
                        else:
                            tqdm.write(f"Info: Scenario {i} missing equity_curve - this will be filtered out")
            
            if pbar:
                pbar.close()
                
            # Filter out results with missing equity curve
            results = [r for r in results if 'equity_curve' in r and r['equity_curve'] is not None]
            print(f"Returned {len(results)} valid scenarios out of {scenarios} total")
            
            return results

    try:
        # Fall back to sequential processing if only 1 scenario
        if scenarios == 1:
            print("Using sequential processing for Monte Carlo (single scenario)")
            
            if progress_bar:
                if jh.is_notebook():
                    from tqdm.notebook import tqdm
                else:
                    from tqdm import tqdm
                pbar = tqdm(total=scenarios, desc="Monte Carlo Scenarios")
            else:
                pbar = None
                
            _backtest = functools.partial(
                backtest,
                config=config,
                routes=routes,
                data_routes=data_routes,
                candles=candles,
                warmup_candles=warmup_candles,
                generate_equity_curve=True,
                hyperparameters=hyperparameters,
                fast_mode=fast_mode,
                with_candles_pipeline=with_candles_pipeline
            )

            results = []
            for i in range(scenarios):
                result = _backtest(
                    benchmark=benchmark and i == 0, 
                    with_candles_pipeline=i != 0
                )
                results.append(result)
                if pbar:
                    pbar.update(1)
                    if 'equity_curve' not in result or result['equity_curve'] is None:
                        if jh.is_notebook():
                            print(f"Info: Scenario {i} missing equity_curve - this will be filtered out")
                        else:
                            tqdm.write(f"Info: Scenario {i} missing equity_curve - this will be filtered out")
            
            if pbar:
                pbar.close()
            
            # Filter out results with missing equity curve
            results = [r for r in results if 'equity_curve' in r and r['equity_curve'] is not None]
            print(f"Returned {len(results)} valid scenarios out of {scenarios} total")
            
            return results
        
        # Initialize progress bar if requested
        if progress_bar:
            if jh.is_notebook():
                from tqdm.notebook import tqdm
            else:
                from tqdm import tqdm
            pbar = tqdm(total=scenarios, desc="Monte Carlo Scenarios")
        else:
            pbar = None

        # Launch all scenarios in parallel
        refs = []
        for i in range(scenarios):
            ref = ray_run_scenario.remote(
                config=config,
                routes=routes,
                data_routes=data_routes,
                candles=candles,
                warmup_candles=warmup_candles,
                hyperparameters=hyperparameters,
                fast_mode=fast_mode,
                benchmark=benchmark,
                scenario_index=i,
                with_candles_pipeline=with_candles_pipeline
            )
            refs.append(ref)

        # Process results as they complete
        results = []
        total_completed = 0
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
                    total_completed += 1
        
        if pbar:
            pbar.close()
        
        # Filter out results with missing equity curve
        valid_results = [r for r in results if 'equity_curve' in r and r['equity_curve'] is not None]
        filtered_count = len(results) - len(valid_results)
        
        if filtered_count > 0:
            print(f"Filtered out {filtered_count} scenarios with missing equity curves")
        
        print(f"Returned {len(valid_results)} valid scenarios out of {scenarios} total")
        
        return valid_results
    
    except Exception as e:
        print(f"Error during Monte Carlo simulation: {e}")
        raise
    
    finally:
        # Shutdown Ray
        if ray.is_initialized():
            ray.shutdown()
