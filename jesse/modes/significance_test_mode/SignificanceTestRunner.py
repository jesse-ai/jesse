import os
import time
import traceback
from typing import Dict, List, Optional

import jesse.helpers as jh
from jesse.services.progress import publish_status
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

        self.client_id = jh.get_session_id()

    def _raise_if_cancelled(self) -> None:
        """Stop inside the active execution path when cancellation is requested."""
        if not is_process_active(self.client_id):
            raise exceptions.Termination

    def _mark_stopped_unless_terminated(self) -> None:
        """Preserve the explicit terminal status selected by the user."""
        session = get_significance_test_session_by_id(self.session_id)
        if session is None or session.status not in {'stopped', 'terminated'}:
            update_significance_test_session_status(self.session_id, 'stopped')

    def run(self) -> None:
        try:
            jh.debug(f"Rule Significance Test started: {self.n_simulations} simulations")
            self._raise_if_cancelled()
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
            self._mark_stopped_unless_terminated()
            raise

        except Exception as e:
            error_traceback = traceback.format_exc()
            error = f'{type(e).__name__}: {e}'
            update_significance_test_session_status(self.session_id, 'stopped')
            store_significance_test_exception(self.session_id, error, error_traceback)
            sync_publish('exception', {
                'error': error,
                'traceback': error_traceback
            })
            raise

    def _publish_general_info(self):
        sync_publish('general_info', {
            'started_at': jh.timestamp_to_arrow(self.start_time).humanize(
                jh.timestamp_to_arrow(jh.now(force_fresh=True))
            ),
            'n_simulations': self.n_simulations,
        })

    def _run_significance_test(self):
        from jesse.research.rule_significance_testing import rule_significance_test, plot_significance_test

        # Build config same format as research.backtest()
        exchange_config = self.user_config.get('exchange', {})
        # Fee, balance, and leverage do not affect this signal-only calculation.
        config = {
            'starting_balance': 10000,
            'fee': 0,
            'type': exchange_config.get('type', 'futures'),
            'simulation_model': exchange_config.get('simulation_model'),
            'annualization': exchange_config.get('annualization', 365),
            'futures_leverage': 1,
            'futures_leverage_mode': 'cross',
            'warm_up_candles': self.user_config.get('warm_up_candles', 210),
            'exchange': self.routes[0]['exchange'],
        }

        last_update_time = None
        throttle_interval = 0.5

        def progress_callback(current_progress: int, total_progress: int):
            nonlocal last_update_time
            self._raise_if_cancelled()
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
                    'message': 'Testing randomized strategy signals…',
                    'current': completed_sims,
                    'total': self.n_simulations,
                    'estimated_remaining_seconds': estimated_remaining,
                })
                last_update_time = current_time

        # Signal generation precedes the measurable simulation phase.
        sync_publish('progressbar', {
            'message': 'Calculating strategy signals…',
            'indeterminate': True,
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
        self._raise_if_cancelled()

        # Publish completion progress
        sync_publish('progressbar', {
            'current': self.n_simulations,
            'total': self.n_simulations,
            'estimated_remaining_seconds': 0,
        })

        publish_status('Generating significance charts and saving results…', total=self.n_simulations)
        # Generate chart image (theme-aware)
        charts_folder = os.path.abspath('storage/significance-test-charts')
        chart_path = plot_significance_test(
            result=result,
            charts_folder=charts_folder,
            theme=self.theme,
            show_title=False,
        )
        self._raise_if_cancelled()

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
