from multiprocessing import cpu_count
from typing import Dict, List, Optional
import arrow
import jesse.helpers as jh
from jesse.modes.backtest_mode import load_candles
from jesse.services.validators import validate_routes
from jesse.store import store
from jesse.services.failure import register_custom_exception_handler
from jesse.routes import router
from jesse.models.SignificanceTestSession import (
    update_significance_test_session_status,
    update_significance_test_session_state,
)
from .SignificanceTestRunner import SignificanceTestRunner


def run(
    session_id: str,
    user_config: dict,
    exchange: str,
    routes: List[Dict[str, str]],
    data_routes: List[Dict[str, str]],
    start_date: str,
    finish_date: str,
    n_simulations: int,
    random_seed: Optional[int],
    theme: str,
    state: dict,
) -> None:
    from jesse.config import config, set_config
    config['app']['trading_mode'] = 'significance-test'

    if len(routes) != 1:
        raise ValueError('Rule Significance Test requires exactly one trading route.')

    # Load candles
    set_config(user_config)

    for r in routes:
        r['exchange'] = exchange
    for r in data_routes:
        r['exchange'] = exchange

    router.initiate(routes, data_routes)
    store.app.set_session_id(session_id)
    register_custom_exception_handler()
    validate_routes(router)

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

    # Session is always pre-created by the controller before this task runs;
    # just update it with the strategy codes now that we have them
    update_significance_test_session_status(session_id, 'running')
    update_significance_test_session_state(session_id, state, strategy_codes)

    start_date_timestamp = jh.arrow_to_timestamp(arrow.get(start_date, 'YYYY-MM-DD'))
    finish_date_timestamp = jh.arrow_to_timestamp(arrow.get(finish_date, 'YYYY-MM-DD'))
    warmup_candles, candles = load_candles(start_date_timestamp, finish_date_timestamp)

    runner = SignificanceTestRunner(
        session_id=session_id,
        user_config=user_config,
        routes=routes,
        data_routes=data_routes,
        candles=candles,
        warmup_candles=warmup_candles,
        n_simulations=n_simulations,
        random_seed=random_seed,
        theme=theme,
        cpu_cores=1,
    )
    runner.run()
