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
            print(f"Info: Scenario {scenario_index} missing equity_curve - this will be filtered out")
                
        return result
    except Exception as e:
        # Log and re-raise exceptions
        print(f"Ray scenario {scenario_index} failed with exception: {str(e)}")
        raise

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
                scenarios_list = tqdm(range(scenarios))
            else:
                scenarios_list = range(scenarios)
                
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

            results = [
                _backtest(
                    benchmark=benchmark and i == 0, 
                    with_candles_pipeline=i != 0
                )
                for i in scenarios_list
            ]
            
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
                scenarios_list = tqdm(range(scenarios))
            else:
                scenarios_list = range(scenarios)
                
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

            results = [
                _backtest(
                    benchmark=benchmark and i == 0, 
                    with_candles_pipeline=i != 0
                )
                for i in scenarios_list
            ]
            
            # Filter out results with missing equity curve
            results = [r for r in results if 'equity_curve' in r and r['equity_curve'] is not None]
            print(f"Returned {len(results)} valid scenarios out of {scenarios} total")
            
            return results
        
        # Use Ray for parallel processing
        if progress_bar:
            if jh.is_notebook():
                from tqdm.notebook import tqdm
            else:
                from tqdm import tqdm
            scenarios_list = tqdm(range(scenarios))
        else:
            scenarios_list = range(scenarios)

        # Launch all scenarios in parallel
        refs = []
        for i in scenarios_list:
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

        # Get results, maintaining the order
        results = ray.get(refs)
        
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
