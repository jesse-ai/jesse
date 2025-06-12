from multiprocessing import cpu_count
from typing import Dict, List, Tuple
import arrow
import jesse.helpers as jh
from jesse.modes.backtest_mode import load_candles
from jesse.services.validators import validate_routes
from jesse.store import store
from .Optimize import Optimizer
from jesse.services.failure import register_custom_exception_handler
from jesse.routes import router
from jesse.models.OptimizationSession import store_optimization_session, get_optimization_session_by_id, update_optimization_session_status, update_optimization_session_state


def run(
        session_id: str,
        user_config: dict,
        exchange: str,
        routes: List[Dict[str, str]],
        data_routes: List[Dict[str, str]],
        training_start_date: str,
        training_finish_date: str,
        testing_start_date: str,
        testing_finish_date: str,
        optimal_total: int,
        fast_mode: bool,
        cpu_cores: int,
        state: dict,
) -> None:
    if jh.python_version() == (3, 13):
        raise ValueError(
            'Optimization is not supported on Python 3.13. The "Ray" library used for optimization does not support Python 3.13 yet. Please use Python 3.12 or lower.')

    from jesse.config import config, set_config
    config['app']['trading_mode'] = 'optimize'

    # validate cpu_cores
    if cpu_cores < 1:
        raise ValueError('cpu_cores must be an integer value greater than 0. Please check your settings page for optimization.')
    # get the max number of cores
    max_cpu_cores = cpu_count()
    if cpu_cores > max_cpu_cores:
        raise ValueError(f'cpu_cores must be less than or equal to {max_cpu_cores} which is the number of cores on your machine.')

    # inject config
    set_config(user_config)
    # add exchange to routes
    for r in routes:
        r['exchange'] = exchange
    for r in data_routes:
        r['exchange'] = exchange
    # set routes
    router.initiate(routes, data_routes)
    store.app.set_session_id(session_id)
    register_custom_exception_handler()
    # validate routes
    validate_routes(router)

    # load historical candles
    training_warmup_candles, training_candles, testing_warmup_candles, testing_candles = _get_training_and_testing_candles(
        training_start_date,
        training_finish_date,
        testing_start_date,
        testing_finish_date
    )

    # Check if we're resuming an existing session
    existing_session = get_optimization_session_by_id(session_id)

    if existing_session:
        # Session exists, update it for resuming
        update_optimization_session_status(session_id, 'running')
        update_optimization_session_state(session_id, state)

        if jh.is_debugging():
            jh.debug(f"Resuming existing optimization session with ID: {session_id}")
    else:
        # Session doesn't exist, create a new one
        store_optimization_session(
            id=session_id,
            status='running'
        )
        update_optimization_session_state(session_id, state)

        if jh.is_debugging():
            jh.debug(f"Created new optimization session with ID: {session_id}")

    optimizer = Optimizer(
        session_id,
        user_config,
        training_warmup_candles,
        training_candles,
        testing_warmup_candles,
        testing_candles,
        fast_mode,
        optimal_total,
        cpu_cores
    )

    optimizer.run()


def _get_training_and_testing_candles(
        training_start_date: str,
        training_finish_date: str,
        testing_start_date: str,
        testing_finish_date: str
) -> Tuple[dict, dict, dict, dict]:
    training_start_date_timestamp = jh.arrow_to_timestamp(arrow.get(training_start_date, 'YYYY-MM-DD'))
    training_finish_date_timestamp = jh.arrow_to_timestamp(arrow.get(training_finish_date, 'YYYY-MM-DD'))
    testing_start_date_timestamp = jh.arrow_to_timestamp(arrow.get(testing_start_date, 'YYYY-MM-DD'))
    testing_finish_date_timestamp = jh.arrow_to_timestamp(arrow.get(testing_finish_date, 'YYYY-MM-DD'))

    # fetch training candles
    training_warmup_candles, training_candles = load_candles(training_start_date_timestamp, training_finish_date_timestamp)
    # fetch testing candles
    testing_warmup_candles, testing_candles = load_candles(testing_start_date_timestamp, testing_finish_date_timestamp)

    return training_warmup_candles, training_candles, testing_warmup_candles, testing_candles
