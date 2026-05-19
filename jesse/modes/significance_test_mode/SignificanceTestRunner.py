import os
import time
import traceback
from datetime import timedelta
from typing import Dict, List, Optional

import jesse.helpers as jh
from jesse import exceptions
from jesse.services.redis import sync_publish, is_process_active
from jesse.models.SignificanceTestSession import (
    update_significance_test_session_status,
    update_significance_test_session_results,
    store_significance_test_exception,
    get_significance_test_session_by_id,
)


class SignificanceTestRunner:
    def __init__(
        self,
        session_id: str,
        user_config: dict,
        routes: List[Dict[str, str]],
        data_routes: List[Dict[str, str]],
        candles: dict,
        warmup_candles: dict,
        n_simulations: int,
        random_seed: Optional[int],
        theme: str,
        **kwargs,
    ):
        self.session_id = session_id
        self.user_config = user_config
        self.routes = routes
        self.data_routes = data_routes
        self.candles = candles
        self.warmup_candles = warmup_candles
        self.n_simulations = n_simulations
        self.random_seed = random_seed if random_seed is not None else 42
        self.theme = theme

        self.start_time = jh.now_to_timestamp()

        # Periodic termination check
        client_id = jh.get_session_id()
        from timeloop import Timeloop
        self.tl = Timeloop()

        @self.tl.job(interval=timedelta(seconds=1))
        def check_for_termination():
            if is_process_active(client_id) is False:
                session = get_significance_test_session_by_id(self.session_id)
                if session and session.status != 'terminated':
                    update_significance_test_session_status(self.session_id, 'stopped')
                raise exceptions.Termination

        self.tl.start()

    def run(self) -> None:
        jh.debug(f"Rule Significance Test started: {self.n_simulations} simulations")

        try:
            self._publish_general_info()
            self._run_significance_test()
            update_significance_test_session_status(self.session_id, 'finished')
            
            finish_time = jh.now_to_timestamp()
            execution_duration = round((finish_time - self.start_time) / 1000, 2)
            
            sync_publish('alert', {
                'message': f"Successfully executed rule significance test in: {execution_duration} seconds",
                'type': 'success'
            })

        except exceptions.Termination:
            update_significance_test_session_status(self.session_id, 'stopped')
            raise

        except Exception as e:
            error_traceback = traceback.format_exc()
            update_significance_test_session_status(self.session_id, 'stopped')
            store_significance_test_exception(self.session_id, str(e), error_traceback)
            sync_publish('exception', {
                'error': str(e),
                'traceback': error_traceback
            })
            raise

        finally:
            try:
                self.tl.stop()
            except Exception:
                pass

    def _publish_general_info(self):
        sync_publish('general_info', {
            'started_at': jh.timestamp_to_arrow(self.start_time).humanize(),
            'n_simulations': self.n_simulations,
        })

    def _run_significance_test(self):
        from jesse.research.rule_significance_testing import rule_significance_test, plot_significance_test

        # Build config same format as research.backtest()
        # Fee, balance, type, leverage are hardcoded - they do not affect rule significance testing
        config = {
            'starting_balance': 10000,
            'fee': 0,
            'type': 'futures',
            'futures_leverage': 1,
            'futures_leverage_mode': 'cross',
            'warm_up_candles': self.user_config.get('warm_up_candles', 210),
            'exchange': self.routes[0]['exchange'],
        }

        last_update_time = None
        throttle_interval = 0.5

        def progress_callback(current_progress: int, total_progress: int):
            nonlocal last_update_time
            current_time = time.time()
            should_publish = (
                last_update_time is None
                or (current_time - last_update_time) >= throttle_interval
                or current_progress == total_progress
            )
            if should_publish:
                elapsed = jh.now_to_timestamp() - self.start_time
                completed_sims = int((current_progress / total_progress) * self.n_simulations) if total_progress > 0 else 0
                if completed_sims > 0:
                    avg = elapsed / completed_sims
                    estimated_remaining = int(avg * (self.n_simulations - completed_sims))
                else:
                    estimated_remaining = 0
                sync_publish('progressbar', {
                    'current': completed_sims,
                    'total': self.n_simulations,
                    'estimated_remaining_seconds': estimated_remaining,
                })
                last_update_time = current_time

        # Publish initial progress
        sync_publish('progressbar', {
            'current': 0,
            'total': self.n_simulations,
            'estimated_remaining_seconds': 0,
        })

        result = rule_significance_test(
            config=config,
            routes=self.routes,
            data_routes=self.data_routes,
            candles=self.candles,
            warmup_candles=self.warmup_candles,
            n_simulations=self.n_simulations,
            random_seed=self.random_seed,
            progress_bar=False,
            progress_callback=progress_callback,
        )

        # Publish completion progress
        sync_publish('progressbar', {
            'current': self.n_simulations,
            'total': self.n_simulations,
            'estimated_remaining_seconds': 0,
        })

        # Generate chart image (theme-aware)
        charts_folder = os.path.abspath('storage/significance-test-charts')
        chart_path = plot_significance_test(
            result=result,
            charts_folder=charts_folder,
            theme=self.theme,
            show_title=False,
        )



        # Store safe serializable results (simulated_means is a numpy array → list)
        safe_result = {
            'observed_mean': float(result['observed_mean']),
            'annualized_return': float(result['annualized_return']),
            'p_value': float(result['p_value']),
            'n_simulations': int(result['n_simulations']),
            'n_observations': int(result['n_observations']),
            # Don't store the full simulated_means array in the DB — too large
        }

        update_significance_test_session_results(
            session_id=self.session_id,
            results=safe_result,
            chart_path=chart_path,
        )

        sync_publish('results', safe_result)
