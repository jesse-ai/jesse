from datetime import timedelta
from multiprocessing import cpu_count
from typing import Dict, List, Optional
import os
import ray
import numpy as np
import jesse.helpers as jh
import jesse.services.logger as logger
from jesse import exceptions
from jesse.services.redis import sync_publish, is_process_active
from jesse.services.progressbar import Progressbar
from jesse.research.monte_carlo import (
    monte_carlo_trades,
    monte_carlo_candles,
    GaussianNoiseCandlesPipeline,
    MovingBlockBootstrapCandlesPipeline
)
from jesse.models.MonteCarloSession import (
    update_monte_carlo_session_status,
    store_trades_session,
    update_trades_session_progress,
    update_trades_session_status,
    store_candles_session,
    update_candles_session_progress,
    update_candles_session_status,
    store_session_exception,
    append_session_logs,
    get_monte_carlo_session_by_id
)
import traceback


class MonteCarloRunner:
    def __init__(
        self,
        session_id: str,
        user_config: dict,
        routes: List[Dict[str, str]],
        data_routes: List[Dict[str, str]],
        candles: dict,
        warmup_candles: dict,
        run_trades: bool,
        run_candles: bool,
        num_scenarios: int,
        fast_mode: bool,
        cpu_cores: int,
        pipeline_type: Optional[str],
        pipeline_params: Optional[dict],
    ):
        if jh.python_version() == (3, 13):
            raise ValueError(
                'Monte Carlo mode is not supported on Python 3.13. The Ray library does not support Python 3.13 yet. Please use Python 3.12 or lower.')

        self.session_id = session_id
        self.user_config = user_config
        self.routes = routes
        self.data_routes = data_routes
        self.candles = candles
        self.warmup_candles = warmup_candles
        self.run_trades = run_trades
        self.run_candles = run_candles
        self.num_scenarios = num_scenarios
        self.fast_mode = fast_mode
        self.pipeline_type = pipeline_type
        self.pipeline_params = pipeline_params or {}

        # Validate and set CPU cores
        if cpu_cores < 1:
            raise ValueError('cpu_cores must be an integer value greater than 0.')
        available = cpu_count()
        self.cpu_cores = cpu_cores if cpu_cores <= available else available

        self.start_time = jh.now_to_timestamp()
        
        # Create progress bar for tracking
        self.progressbar = Progressbar(num_scenarios)

        # Initialize Ray if not already
        self.ray_started_here = False
        if not ray.is_initialized():
            try:
                ray.init(num_cpus=self.cpu_cores, ignore_reinit_error=True)
                logger.log_monte_carlo(f"Successfully started Monte Carlo session with {self.cpu_cores} CPU cores", session_id=self.session_id)
                self.ray_started_here = True
            except Exception as e:
                logger.log_monte_carlo(f"Error initializing Ray: {e}. Falling back to 1 CPU.", session_id=self.session_id)
                self.cpu_cores = 1
                ray.init(num_cpus=1, ignore_reinit_error=True)
                self.ray_started_here = True

        # Setup periodic termination check
        client_id = jh.get_session_id()
        from timeloop import Timeloop
        self.tl = Timeloop()

        @self.tl.job(interval=timedelta(seconds=1))
        def check_for_termination():
            if is_process_active(client_id) is False:
                # Update session status to 'stopped' in the database
                if get_monte_carlo_session_by_id(self.session_id).status != 'terminated':
                    update_monte_carlo_session_status(self.session_id, 'stopped')
                raise exceptions.Termination
        
        self.tl.start()

        # Track session IDs
        self.trades_session_id = None
        self.candles_session_id = None

    def run(self) -> None:
        logger.log_monte_carlo(f"Monte Carlo session started with {self.cpu_cores} CPU cores", session_id=self.session_id)
        logger.log_monte_carlo(f"Run trades: {self.run_trades}, Run candles: {self.run_candles}", session_id=self.session_id)

        try:
            # Publish general info
            self._publish_general_info()

            # Run trades first (faster)
            if self.run_trades:
                logger.log_monte_carlo("Starting trades simulation...", session_id=self.session_id)
                self._run_trades_simulation()
                logger.log_monte_carlo("Trades simulation completed", session_id=self.session_id)

            # Then run candles
            if self.run_candles:
                logger.log_monte_carlo("Starting candles simulation...", session_id=self.session_id)
                self._run_candles_simulation()
                logger.log_monte_carlo("Candles simulation completed", session_id=self.session_id)

            # Update parent session status to 'finished'
            update_monte_carlo_session_status(self.session_id, 'finished')

            # Publish completion alert
            sync_publish('alert', {
                'message': f"Monte Carlo simulation completed successfully!",
                'type': 'success'
            })

        except exceptions.Termination:
            logger.log_monte_carlo("Monte Carlo simulation terminated by user", session_id=self.session_id)
            update_monte_carlo_session_status(self.session_id, 'stopped')
            raise
        except Exception as e:
            error_traceback = traceback.format_exc()
            error_type = type(e).__name__
            logger.log_monte_carlo(f"ERROR: Monte Carlo simulation failed with {error_type}: {str(e)}", session_id=self.session_id)
            logger.log_monte_carlo(f"Traceback:\n{error_traceback}", session_id=self.session_id)
            update_monte_carlo_session_status(self.session_id, 'stopped')
            
            # Store exception in the appropriate child session
            if self.trades_session_id and not self.candles_session_id:
                store_session_exception(self.trades_session_id, 'trades', str(e), error_traceback)
            elif self.candles_session_id:
                store_session_exception(self.candles_session_id, 'candles', str(e), error_traceback)
            
            # Publish exception to frontend
            sync_publish('exception', {
                'error': str(e),
                'traceback': error_traceback
            })
            
            raise
        finally:
            if self.ray_started_here and ray.is_initialized():
                ray.shutdown()

    def _publish_general_info(self):
        general_info = {
            'started_at': jh.timestamp_to_arrow(self.start_time).humanize(),
            'run_trades': self.run_trades,
            'run_candles': self.run_candles,
            'num_scenarios': self.num_scenarios,
            'exchange_type': self.user_config['exchange']['type'],
            'leverage_mode': self.user_config['exchange'].get('futures_leverage_mode', 'N/A'),
            'leverage': self.user_config['exchange'].get('futures_leverage', 'N/A'),
            'cpu_cores': self.cpu_cores,
        }
        sync_publish('general_info', general_info)

    def _run_trades_simulation(self):
        # Create trades child session in DB
        self.trades_session_id = store_trades_session(
            parent_id=self.session_id,
            num_scenarios=self.num_scenarios
        )

        # Publish initial progress for trades
        sync_publish('trades_progressbar', {
            'current': 0,
            'total': self.num_scenarios,
            'estimated_remaining_seconds': 0
        })

        # Prepare config - flatten the structure from settings
        config = {
            'starting_balance': self.user_config.get('starting_balance', 10000),
            'fee': self.user_config.get('fee', 0.0005),
            'type': self.user_config.get('exchange', {}).get('type', 'futures'),
            'futures_leverage': self.user_config.get('exchange', {}).get('futures_leverage', 1),
            'futures_leverage_mode': self.user_config.get('exchange', {}).get('futures_leverage_mode', 'cross'),
            'warm_up_candles': self.user_config.get('warm_up_candles', 210),
            'exchange': self.routes[0]['exchange']
        }

        try:
            # Call monte_carlo_trades from research module with progress tracking
            results = self._run_trades_with_progress(config)

            # Extract summary metrics for display
            summary_metrics = self._extract_trades_summary_metrics(results)

            # Store results
            update_trades_session_progress(
                id=self.trades_session_id,
                completed=results.get('num_scenarios', self.num_scenarios),
                results=results
            )
            update_trades_session_status(self.trades_session_id, 'finished')

            # Publish results
            sync_publish('monte_carlo_trades_summary', summary_metrics)
            sync_publish('monte_carlo_trades_results', results)

            # Log completion
            log_msg = f"Trades simulation completed: {results.get('num_scenarios', 0)} scenarios"
            append_session_logs(self.trades_session_id, 'trades', log_msg)

        except Exception as e:
            error_traceback = traceback.format_exc()
            error_type = type(e).__name__
            logger.log_monte_carlo(f"ERROR: Trades simulation failed with {error_type}: {str(e)}", session_id=self.session_id)
            logger.log_monte_carlo(f"Traceback:\n{error_traceback}", session_id=self.session_id)
            
            # Store exception in database
            store_session_exception(self.trades_session_id, 'trades', str(e), error_traceback)
            update_trades_session_status(self.trades_session_id, 'stopped')
            
            # Publish exception to frontend
            sync_publish('exception', {
                'error': str(e),
                'traceback': error_traceback
            })
            
            raise

    def _run_candles_simulation(self):
        # Create candles child session in DB
        self.candles_session_id = store_candles_session(
            parent_id=self.session_id,
            num_scenarios=self.num_scenarios,
            pipeline_type=self.pipeline_type,
            pipeline_params=self.pipeline_params
        )

        # Publish initial progress for candles
        sync_publish('candles_progressbar', {
            'current': 0,
            'total': self.num_scenarios,
            'estimated_remaining_seconds': 0
        })

        # Prepare config - flatten the structure from settings
        config = {
            'starting_balance': self.user_config.get('starting_balance', 10000),
            'fee': self.user_config.get('fee', 0.0005),
            'type': self.user_config.get('exchange', {}).get('type', 'futures'),
            'futures_leverage': self.user_config.get('exchange', {}).get('futures_leverage', 1),
            'futures_leverage_mode': self.user_config.get('exchange', {}).get('futures_leverage_mode', 'cross'),
            'warm_up_candles': self.user_config.get('warm_up_candles', 210),
            'exchange': self.routes[0]['exchange']
        }

        # Prepare pipeline
        pipeline_class = None
        pipeline_kwargs = self.pipeline_params.copy()

        if self.pipeline_type == 'gaussian':
            pipeline_class = GaussianNoiseCandlesPipeline
            # Set defaults if not provided
            if 'close_sigma' not in pipeline_kwargs:
                pipeline_kwargs['close_sigma'] = 0.001
            if 'high_sigma' not in pipeline_kwargs:
                pipeline_kwargs['high_sigma'] = 0.0001
            if 'low_sigma' not in pipeline_kwargs:
                pipeline_kwargs['low_sigma'] = 0.0001
        else:  # moving_block_bootstrap
            pipeline_class = MovingBlockBootstrapCandlesPipeline

        # Ensure batch_size is set
        if 'batch_size' not in pipeline_kwargs:
            pipeline_kwargs['batch_size'] = 10080  # 7 days

        try:
            logger.log_monte_carlo(f"Calling _run_candles_with_progress with {self.num_scenarios} scenarios", session_id=self.session_id)
            logger.log_monte_carlo(f"Pipeline: {self.pipeline_type}, kwargs: {pipeline_kwargs}", session_id=self.session_id)
            
            # Call monte_carlo_candles from research module with progress tracking
            results = self._run_candles_with_progress(config, pipeline_class, pipeline_kwargs)
            
            logger.log_monte_carlo(f"Candles simulation returned {len(results.get('scenarios', []))} scenarios", session_id=self.session_id)

            # Extract summary metrics for display
            summary_metrics = self._extract_candles_summary_metrics(results)

            # Store results
            update_candles_session_progress(
                id=self.candles_session_id,
                completed=results.get('num_scenarios', self.num_scenarios),
                results=results
            )
            update_candles_session_status(self.candles_session_id, 'finished')

            # Publish results
            sync_publish('monte_carlo_candles_summary', summary_metrics)
            sync_publish('monte_carlo_candles_results', results)

            # Log completion
            log_msg = f"Candles simulation completed: {results.get('num_scenarios', 0)} scenarios"
            append_session_logs(self.candles_session_id, 'candles', log_msg)

        except Exception as e:
            error_traceback = traceback.format_exc()
            error_type = type(e).__name__
            logger.log_monte_carlo(f"ERROR: Candles simulation failed with {error_type}: {str(e)}", session_id=self.session_id)
            logger.log_monte_carlo(f"Traceback:\n{error_traceback}", session_id=self.session_id)
            
            # Store exception in database
            store_session_exception(self.candles_session_id, 'candles', str(e), error_traceback)
            update_candles_session_status(self.candles_session_id, 'stopped')
            
            # Publish exception to frontend
            sync_publish('exception', {
                'error': str(e),
                'traceback': error_traceback
            })
            
            raise

    def _run_trades_with_progress(self, config: dict) -> dict:
        """Run trades simulation with progress tracking"""
        import time
        
        # Reset progressbar for this simulation
        self.progressbar = Progressbar(self.num_scenarios)
        self.start_time = jh.now_to_timestamp()
        last_update_time = None
        throttle_interval = 0.5  # Only publish every 0.5 seconds
        
        def progress_callback(completed_count: int):
            """Called when scenarios complete to update progress"""
            nonlocal last_update_time
            
            if completed_count <= self.num_scenarios:
                current_time = time.time()
                
                # Only publish if enough time has passed or it's the last update
                should_publish = (
                    last_update_time is None or 
                    (current_time - last_update_time) >= throttle_interval or
                    completed_count == self.num_scenarios
                )
                
                if should_publish:
                    # Calculate estimated remaining time
                    elapsed = jh.now_to_timestamp() - self.start_time
                    if completed_count > 0:
                        avg_time_per_scenario = elapsed / completed_count
                        remaining_scenarios = self.num_scenarios - completed_count
                        estimated_remaining = int(avg_time_per_scenario * remaining_scenarios)
                    else:
                        estimated_remaining = 0
                    
                    sync_publish('trades_progressbar', {
                        'current': completed_count,
                        'total': self.num_scenarios,
                        'estimated_remaining_seconds': estimated_remaining
                    })
                    
                    last_update_time = current_time
        
        results = monte_carlo_trades(
            config=config,
            routes=self.routes,
            data_routes=self.data_routes,
            candles=self.candles,
            warmup_candles=self.warmup_candles,
            benchmark=False,
            hyperparameters=None,
            fast_mode=self.fast_mode,
            num_scenarios=self.num_scenarios,
            progress_bar=False,
            cpu_cores=self.cpu_cores,
            progress_callback=progress_callback,
            result_callback=None
        )
        
        # Publish completion
        sync_publish('trades_progressbar', {
            'current': self.num_scenarios,
            'total': self.num_scenarios,
            'estimated_remaining_seconds': 0
        })
        
        return results

    def _run_candles_with_progress(self, config: dict, pipeline_class, pipeline_kwargs: dict) -> dict:
        """Run candles simulation with progress tracking"""
        import time
        
        logger.log_monte_carlo("Inside _run_candles_with_progress", session_id=self.session_id)
        
        # Reset start time for this simulation
        self.start_time = jh.now_to_timestamp()
        last_update_time = None
        throttle_interval = 0.5  # Only publish every 0.5 seconds
        
        def progress_callback(completed_count: int):
            """Called when scenarios complete to update progress"""
            nonlocal last_update_time
            
            if completed_count <= self.num_scenarios:
                current_time = time.time()
                
                # Only publish if enough time has passed or it's the last update
                should_publish = (
                    last_update_time is None or 
                    (current_time - last_update_time) >= throttle_interval or
                    completed_count == self.num_scenarios
                )
                
                if should_publish:
                    # Calculate estimated remaining time
                    elapsed = jh.now_to_timestamp() - self.start_time
                    if completed_count > 0:
                        avg_time_per_scenario = elapsed / completed_count
                        remaining_scenarios = self.num_scenarios - completed_count
                        estimated_remaining = int(avg_time_per_scenario * remaining_scenarios)
                    else:
                        estimated_remaining = 0
                    
                    sync_publish('candles_progressbar', {
                        'current': completed_count,
                        'total': self.num_scenarios,
                        'estimated_remaining_seconds': estimated_remaining
                    })
                    
                    last_update_time = current_time
        
        logger.log_monte_carlo(f"About to call monte_carlo_candles with {len(self.candles)} candle datasets", session_id=self.session_id)
        
        results = monte_carlo_candles(
            config=config,
            routes=self.routes,
            data_routes=self.data_routes,
            candles=self.candles,
            warmup_candles=self.warmup_candles,
            hyperparameters=None,
            fast_mode=self.fast_mode,
            num_scenarios=self.num_scenarios,
            progress_bar=False,
            candles_pipeline_class=pipeline_class,
            candles_pipeline_kwargs=pipeline_kwargs,
            cpu_cores=self.cpu_cores,
            progress_callback=progress_callback,
            result_callback=None
        )
        
        # Publish completion
        sync_publish('candles_progressbar', {
            'current': self.num_scenarios,
            'total': self.num_scenarios,
            'estimated_remaining_seconds': 0
        })
        
        return results

    def _extract_trades_summary_metrics(self, results: dict) -> list:
        """Extract summary metrics from trades results for table display"""
        metrics = []
        
        if 'confidence_analysis' not in results or 'metrics' not in results['confidence_analysis']:
            return metrics

        ca_metrics = results['confidence_analysis']['metrics']
        
        # Define metrics to display (in order)
        metric_keys = ['total_return', 'max_drawdown', 'sharpe_ratio', 'calmar_ratio']
        
        for key in metric_keys:
            if key not in ca_metrics:
                continue
                
            analysis = ca_metrics[key]
            original = analysis.get('original', None)
            percentiles = analysis.get('percentiles', {})
            
            # Get percentiles
            p5 = percentiles.get('5th', None)
            p50 = percentiles.get('50th', None)
            p95 = percentiles.get('95th', None)
            
            metrics.append({
                'metric': key,
                'original': original,
                'worst_5': p5,
                'median': p50,
                'best_5': p95
            })
        
        return metrics

    def _extract_candles_summary_metrics(self, results: dict) -> list:
        """Extract summary metrics from candles results for table display"""
        metrics = []
        
        if 'scenarios' not in results or not results['scenarios']:
            return metrics

        original_result = results.get('original')
        simulation_results = results.get('scenarios', [])
        
        if not simulation_results:
            return metrics

        # Metrics to display (in order)
        metric_keys = [
            'net_profit_percentage', 'max_drawdown', 'sharpe_ratio', 
            'win_rate', 'total', 'annual_return', 'calmar_ratio'
        ]

        # Collect values for each metric
        for key in metric_keys:
            values = []
            for scenario in simulation_results:
                if 'metrics' in scenario and key in scenario['metrics']:
                    val = scenario['metrics'][key]
                    if isinstance(val, (int, float)) and np.isfinite(val):
                        values.append(float(val))
            
            if not values:
                continue
            
            arr = np.array(values)
            p5 = np.percentile(arr, 5)
            p50 = np.percentile(arr, 50)
            p95 = np.percentile(arr, 95)
            
            # Get original value from original backtest and normalize if needed
            original = None
            if original_result and 'metrics' in original_result and key in original_result['metrics']:
                original = original_result['metrics'][key]
                if isinstance(original, (int, float)) and np.isfinite(original):
                    original = float(original)
            
            metrics.append({
                'metric': key,
                'original': original,
                'worst_5': p5,
                'median': p50,
                'best_5': p95
            })
        
        return metrics


