"""
Signal-only backtest simulator.

Mirrors jesse/modes/backtest_mode._step_simulator() but skips all order
submission and execution.  At each bar the strategy's _execute_for_signal_test()
is called, which runs before() / should_long() / should_short() / after() without
opening or closing any positions.

The result is three aligned arrays:
  bar_timestamps  – ms timestamp of each closed bar
  close_prices    – closing price of each bar
  signals         – integer signal emitted by the strategy (+1 / -1 / 0)
"""

import copy
import numpy as np
from typing import List, Dict, Optional

import jesse.helpers as jh
from jesse.config import config as jesse_config, reset_config, set_config
from jesse.routes import router
from jesse.store import store
from jesse.services import candle_service, exchange_service, order_service, position_service
from jesse.services.validators import validate_routes
from jesse.constants import TIMEFRAME_TO_ONE_MINUTES
from jesse.modes.backtest_mode import (
    _prepare_routes,
    _prepare_times_before_simulation,
    _get_fixed_jumped_candle,
)

# Reuse _format_config from the research backtest module so the config dict
# accepted here is identical to what backtest() and monte_carlo_candles() accept.
from jesse.research.backtest import _format_config


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
    # ------------------------------------------------------------------
    # Initialisation – identical to _isolated_backtest()
    # ------------------------------------------------------------------
    jesse_config['app']['trading_mode'] = 'backtest'
    set_config(_format_config(config))

    router.initiate(routes, data_routes)
    store.reset()
    validate_routes(router)
    store.candles.init_storage(5000)
    exchange_service.initialize_exchanges_state()
    order_service.initialize_orders_state()
    position_service.initialize_positions_state()

    # Deep-copy to avoid mutating the caller's candle arrays (important when
    # the caller runs multiple parallel experiments).
    trading_candles = copy.deepcopy(candles)
    warmup_candles_copy = copy.deepcopy(warmup_candles) if warmup_candles else None

    # Inject warm-up candles when provided
    if warmup_candles_copy:
        for c in jesse_config['app']['considering_candles']:
            key = jh.key(c[0], c[1])
            candle_service.inject_warmup_candles_to_store(
                warmup_candles_copy[key]['candles'],
                c[0],
                c[1],
            )

    # ------------------------------------------------------------------
    # Strategy / route preparation
    # ------------------------------------------------------------------
    # _prepare_routes() instantiates the strategy class, sets exchange /
    # symbol / timeframe on it, and calls _init_objects() which wires up
    # self.position, self.broker, etc. — exactly as in a normal backtest.
    _prepare_routes(hyperparameters=hyperparameters, with_candles_pipeline=False)
    _prepare_times_before_simulation(trading_candles)

    # ------------------------------------------------------------------
    # Simulation loop
    # ------------------------------------------------------------------
    key = (
        f"{jesse_config['app']['considering_candles'][0][0]}"
        f"-{jesse_config['app']['considering_candles'][0][1]}"
    )
    first_candles_set = trading_candles[key]['candles']
    length = len(first_candles_set)

    route = router.routes[0]
    bar_minutes = TIMEFRAME_TO_ONE_MINUTES[route.timeframe]

    bar_timestamps: List[int] = []
    close_prices: List[float] = []
    signals: List[int] = []

    for i in range(length):
        if progress_callback:
            progress_callback(i + 1, length)

        # Advance the global clock (same as the normal simulator)
        store.app.time = first_candles_set[i][0] + 60_000

        # ---- Feed candles for every route/data-route symbol ----
        for j in trading_candles:
            short_candle = trading_candles[j]['candles'][i].copy()

            # Fix gap-open prices (carry previous close → current open)
            if i != 0:
                short_candle = _get_fixed_jumped_candle(
                    trading_candles[j]['candles'][i - 1], short_candle
                )

            exc = trading_candles[j]['exchange']
            sym = trading_candles[j]['symbol']

            # Add the 1-minute candle to the store.
            # We skip _simulate_price_change_effect() because there are no
            # orders to process — the whole point is to never open positions.
            candle_service.add_candle(
                short_candle, exc, sym, '1m',
                with_execution=False, with_generation=False,
            )

            # Generate and store aggregated candles for higher timeframes
            # whenever a complete bar has accumulated.
            for timeframe in jesse_config['app']['considering_timeframes']:
                if timeframe == '1m':
                    continue
                tf_minutes = TIMEFRAME_TO_ONE_MINUTES[timeframe]
                if (i + 1) % tf_minutes == 0:
                    generated = candle_service.generate_candle_from_one_minutes(
                        timeframe,
                        trading_candles[j]['candles'][(i - tf_minutes + 1):(i + 1)],
                    )
                    candle_service.add_candle(
                        generated, exc, sym, timeframe,
                        with_execution=False, with_generation=False,
                    )

        # ---- Collect signal when a complete bar has formed ----
        # For 1m strategies fire every minute; for larger timeframes fire only
        # when the bar count is divisible by bar_minutes.
        should_fire = (route.timeframe == '1m') or ((i + 1) % bar_minutes == 0)
        if should_fire:
            signal, cp = route.strategy._execute_for_signal_test()
            bar_timestamps.append(store.app.time)
            close_prices.append(cp)
            signals.append(signal)

        # NOTE: order_service.update_active_orders() and
        #       execute_simulated_market_orders() are intentionally omitted —
        #       no orders are ever submitted, so there is nothing to process.

    # ------------------------------------------------------------------
    # Cleanup – same as _isolated_backtest()
    # ------------------------------------------------------------------
    reset_config()
    store.reset()

    return (
        np.array(bar_timestamps, dtype=np.int64),
        np.array(close_prices, dtype=np.float64),
        np.array(signals, dtype=np.int8),
    )
