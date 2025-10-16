from multiprocessing import cpu_count
from typing import Dict, List, Optional
import arrow
import jesse.helpers as jh
from jesse.modes.backtest_mode import load_candles
from jesse.services.validators import validate_routes
from jesse.store import store
from .MonteCarloRunner import MonteCarloRunner
from jesse.services.failure import register_custom_exception_handler
from jesse.routes import router
from jesse.models.MonteCarloSession import (
    store_monte_carlo_session, 
    get_monte_carlo_session_by_id, 
    update_monte_carlo_session_status,
    update_monte_carlo_session_state
)


def run(
    session_id: str,
    user_config: dict,
    exchange: str,
    routes: List[Dict[str, str]],
    data_routes: List[Dict[str, str]],
    start_date: str,
    finish_date: str,
    run_trades: bool,
    run_candles: bool,
    num_scenarios: int,
    fast_mode: bool,
    cpu_cores: int,
    pipeline_type: Optional[str],
    pipeline_params: Optional[dict],
    state: dict,
) -> None:
    if jh.python_version() == (3, 13):
        raise ValueError(
            'Monte Carlo mode is not supported on Python 3.13. The "Ray" library used for Monte Carlo does not support Python 3.13 yet. Please use Python 3.12 or lower.')

    from jesse.config import config, set_config
    config['app']['trading_mode'] = 'monte-carlo'

    # Validate at least one type is selected
    if not run_trades and not run_candles:
        raise ValueError('At least one Monte Carlo type (trades or candles) must be selected.')

    # Validate cpu_cores
    if cpu_cores < 1:
        raise ValueError('cpu_cores must be an integer value greater than 0. Please check your settings page.')
    
    max_cpu_cores = cpu_count()
    if cpu_cores > max_cpu_cores:
        raise ValueError(f'cpu_cores must be less than or equal to {max_cpu_cores} which is the number of cores on your machine.')

    # Inject config
    set_config(user_config)
    
    # Add exchange to routes
    for r in routes:
        r['exchange'] = exchange
    for r in data_routes:
        r['exchange'] = exchange
    
    # Set routes
    router.initiate(routes, data_routes)
    store.app.set_session_id(session_id)
    register_custom_exception_handler()
    
    # Validate routes
    validate_routes(router)

    # Capture strategy codes for each route (fast operation) BEFORE expensive work
    import os
    strategy_codes = {}
    for r in router.routes:
        key = f"{r.exchange}-{r.symbol}"
        if key not in strategy_codes:
            try:
                strategy_path = f'strategies/{r.strategy_name}/__init__.py'
                if os.path.exists(strategy_path):
                    with open(strategy_path, 'r') as f:
                        content = f.read()
                    strategy_codes[key] = content
            except Exception:
                pass

    # Ensure the parent session exists in DB BEFORE loading candles so the UI can query it
    existing_session = get_monte_carlo_session_by_id(session_id)
    if existing_session:
        update_monte_carlo_session_status(session_id, 'running')
        update_monte_carlo_session_state(session_id, state)
        if jh.is_debugging():
            jh.debug(f"Resuming existing Monte Carlo session with ID: {session_id}")
    else:
        store_monte_carlo_session(
            id=session_id,
            status='running',
            state=state,
            strategy_codes=strategy_codes if strategy_codes else None
        )
        if jh.is_debugging():
            jh.debug(f"Created new Monte Carlo session with ID: {session_id}")

    # Load historical candles AFTER session is persisted
    start_date_timestamp = jh.arrow_to_timestamp(arrow.get(start_date, 'YYYY-MM-DD'))
    finish_date_timestamp = jh.arrow_to_timestamp(arrow.get(finish_date, 'YYYY-MM-DD'))
    warmup_candles, candles = load_candles(start_date_timestamp, finish_date_timestamp)

    # Create and run Monte Carlo runner
    runner = MonteCarloRunner(
        session_id=session_id,
        user_config=user_config,
        routes=routes,
        data_routes=data_routes,
        candles=candles,
        warmup_candles=warmup_candles,
        run_trades=run_trades,
        run_candles=run_candles,
        num_scenarios=num_scenarios,
        fast_mode=fast_mode,
        cpu_cores=cpu_cores,
        pipeline_type=pipeline_type,
        pipeline_params=pipeline_params
    )

    runner.run()


