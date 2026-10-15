"""
Signal-only backtest simulator.

Uses the normal timestamp replay plan and candle publication path while skipping
all order submission and execution. At each completed route bar the strategy's
_execute_for_signal_test() runs before() / should_long() / should_short() / after()
without opening or closing any positions.

The result is three aligned arrays:
  bar_timestamps  – ms timestamp of each closed bar
  close_prices    – closing price of each bar
  signals         – integer signal emitted by the strategy (+1 / -1 / 0)
"""

import copy
import numpy as np
from typing import List, Dict, Optional

import jesse.helpers as jh
from jesse.config import config as jesse_config, set_config
from jesse.routes import router
from jesse.store import store
from jesse.services import candle_service, exchange_service, order_service, position_service
from jesse.services.validators import validate_routes
from jesse.modes.backtest_mode import (
    _apply_timestamp_replay_event,
    _build_timestamp_replay_plan,
    _prepare_routes,
    _prepare_timestamp_replay_warmup,
)

# Reuse _format_config from the research backtest module so the config dict
# accepted here is identical to what backtest() and monte_carlo_candles() accept.
from jesse.research.backtest import (
    _format_config,
    _reset_research_runtime_state,
    _validate_observed_one_minute_candles,
)


def run_signal_only_backtest(
    config: dict,
    routes: List[Dict[str, str]],
    data_routes: List[Dict[str, str]],
    candles: dict,
    warmup_candles: Optional[dict] = None,
    hyperparameters: Optional[dict] = None,
    progress_callback=None,
) -> tuple:
    """
    Run the Jesse candle engine without executing any orders and collect the
    signal emitted by the strategy at every completed bar.

    Parameters
    ----------
    config : dict
        Same format accepted by research.backtest().
    routes : list[dict]
        Exactly one route (enforced by the caller).
    data_routes : list[dict]
        Any number of data-only routes.
    candles : dict
        1-minute candles keyed by "{exchange}-{symbol}".
    warmup_candles : dict, optional
        Warm-up candles injected before the main simulation.
    hyperparameters : dict, optional
        Hyperparameters forwarded to the strategy.

    Returns
    -------
    bar_timestamps : np.ndarray[int64]   shape (N,)
    close_prices   : np.ndarray[float64] shape (N,)
    signals        : np.ndarray[int8]    shape (N,)
    """
    # Validate before touching process-wide state so malformed input cannot
    # partially initialize a research session.
    _validate_observed_one_minute_candles(candles)
    _reset_research_runtime_state()
    try:
        return _execute_signal_only_backtest(
            config,
            routes,
            data_routes,
            candles,
            warmup_candles,
            hyperparameters,
            progress_callback,
        )
    finally:
        _reset_research_runtime_state()


def _execute_signal_only_backtest(
    config: dict,
    routes: List[Dict[str, str]],
    data_routes: List[Dict[str, str]],
    candles: dict,
    warmup_candles: Optional[dict],
    hyperparameters: Optional[dict],
    progress_callback,
) -> tuple:
    """Execute a signal-only run inside an initialized research runtime."""
    jesse_config['app']['trading_mode'] = 'backtest'
    set_config(_format_config(config))

    router.initiate(routes, data_routes)
    store.reset()
    validate_routes(router)
    store.candles.init_storage(5000)
    store.candles.enforce_warmup = jesse_config['env']['data']['warmup_candles_num'] > 0
    exchange_service.initialize_exchanges_state()
    order_service.initialize_orders_state()
    position_service.initialize_positions_state()

    # Deep-copy to avoid mutating the caller's candle arrays (important when
    # the caller runs multiple parallel experiments).
    trading_candles = copy.deepcopy(candles)
    warmup_candles_copy = copy.deepcopy(warmup_candles) if warmup_candles else None

    # Inject warmup through the same common cutoff used by normal research backtests.
    if warmup_candles_copy:
        # The latest instrument start is the first boundary shared by every stream.
        initial_common_start = max(
            int(candle_data['candles'][0, 0])
            for candle_data in trading_candles.values()
        )
        for c in jesse_config['app']['considering_candles']:
            key = jh.key(c[0], c[1])
            candle_service.inject_warmup_candles_to_store(
                warmup_candles_copy[key]['candles'],
                c[0],
                c[1],
                available_at=initial_common_start,
            )

    # ------------------------------------------------------------------
    # Strategy / route preparation
    # ------------------------------------------------------------------
    # _prepare_routes() instantiates the strategy class, sets exchange /
    # symbol / timeframe on it, and calls _init_objects() which wires up
    # self.position, self.broker, etc. — exactly as in a normal backtest.
    candles_pipelines = _prepare_routes(hyperparameters=hyperparameters, with_candles_pipeline=False)
    route = router.routes[0]
    generating_timeframes = [
        (timeframe, jh.timeframe_to_one_minutes(timeframe))
        for timeframe in jesse_config['app']['considering_timeframes']
        if timeframe != '1m'
    ]
    common_start, events = _build_timestamp_replay_plan(trading_candles, generating_timeframes)
    store.candles.uses_timestamp_buckets = True
    _prepare_timestamp_replay_warmup(trading_candles, common_start)
    store.app.starting_time = common_start
    store.app.time = common_start

    bar_timestamps: List[int] = []
    close_prices: List[float] = []
    signals: List[int] = []

    for event_index, event in enumerate(events):
        if progress_callback:
            progress_callback(event_index + 1, len(events))

        updated_routes, _ = _apply_timestamp_replay_event(
            event,
            trading_candles,
            candles_pipelines,
            process_orders=False,
        )
        if (route.exchange, route.symbol, route.timeframe) in updated_routes:
            signal, cp = route.strategy._execute_for_signal_test()
            bar_timestamps.append(store.app.time)
            close_prices.append(cp)
            signals.append(signal)

        # NOTE: order_service.update_active_orders() and
        #       execute_simulated_market_orders() are intentionally omitted —
        #       no orders are ever submitted, so there is nothing to process.

    return (
        np.array(bar_timestamps, dtype=np.int64),
        np.array(close_prices, dtype=np.float64),
        np.array(signals, dtype=np.int8),
    )
