import os
import time
import re
from typing import Dict, List, Tuple, Optional
import numpy as np
import jesse.helpers as jh
from jesse.services.progress import publish_status
import jesse.services.metrics as stats
from jesse import exceptions
from jesse.config import config
from jesse.enums import timeframes, order_types, sides
from jesse.models import Order, Position
from jesse.modes.utils import save_daily_portfolio_balance
from jesse.candle_pipelines import BaseCandlesPipeline
from jesse.routes import router
from jesse.services import charts
from jesse.services import report
from jesse.services import candle_service
from jesse.services.file import store_logs
from jesse.services.validators import validate_routes
from jesse.store import store
from jesse.services import logger
from jesse.services.failure import register_custom_exception_handler
from jesse.services.redis import sync_publish, is_process_active
from jesse.services import order_service
from jesse.services.progressbar import Progressbar
from jesse.constants import TIMEFRAME_TO_ONE_MINUTES
from jesse.services import candle_service, order_service, position_service, exchange_service
from jesse_rust import candle_from_one_minutes as candle_from_one_minutes_rust


def _raise_if_cancelled(client_id: str) -> None:
    """Stop from the active backtest path when its process marker is removed."""
    if not jh.is_unit_testing() and not is_process_active(client_id):
        raise exceptions.Termination


def run(
        client_id: str,
        debug_mode: bool,
        user_config: dict,
        exchange: str,
        routes: List[Dict[str, str]],
        data_routes: List[Dict[str, str]],
        start_date: str,
        finish_date: str,
        candles: dict = None,
        chart: bool = False,
        csv: bool = False,
        json: bool = False,
        fast_mode: bool = False,
        benchmark: bool = False,
        theme: str = 'light'
) -> None:
    from jesse.config import config
    config['app']['trading_mode'] = 'backtest'

    # debug flag
    config['app']['debug_mode'] = debug_mode

    register_custom_exception_handler()
    _raise_if_cancelled(client_id)

    _execute_backtest(
        client_id, debug_mode, user_config, exchange, routes, data_routes, start_date, finish_date, candles, chart,
        csv, json, fast_mode, benchmark, theme
    )


def _execute_backtest(
        client_id: str,
        debug_mode: bool,
        user_config: dict,
        exchange: str,
        routes: List[Dict[str, str]],
        data_routes: List[Dict[str, str]],
        start_date: str,
        finish_date: str,
        candles: dict = None,
        chart: bool = False,
        csv: bool = False,
        json: bool = False,
        fast_mode: bool = False,
        benchmark: bool = False,
        theme: str = 'light'
):
    """
    Executes the backtest that has been initiated from within the dashboard. The purpose of extracting these
    functionalities into this function is so that in case it fails due to a missing data route, it can add
    it and then re-execute itself.
    """
    from jesse.config import set_config

    # inject config
    if not jh.is_unit_testing():
        set_config(user_config)
    # add exchange to routes
    for r in routes:
        r['exchange'] = exchange
    for r in data_routes:
        r['exchange'] = exchange

    # set routes
    router.initiate(routes, data_routes)
    # reset store
    store.reset()
    # set session id
    store.app.set_session_id(client_id)
    publish_status('Validating routes and preparing the backtest…')
    # validate routes
    validate_routes(router)
    # initiate candle store
    store.candles.init_storage(5000)
    # initialize exchanges state
    exchange_service.initialize_exchanges_state()
    # initialize orders state
    order_service.initialize_orders_state()
    # initialize positions state
    position_service.initialize_positions_state()

    # Store backtest session in database (only for UI dashboard, not for CLI/research)
    if not jh.should_execute_silently():
        from jesse.models.BacktestSession import store_backtest_session
        store_backtest_session(
            id=client_id,
            status='running'
        )

    # load historical candles
    if candles is None:
        try:
            publish_status('Loading historical candles…')
            warmup_candles, candles = load_candles(
                jh.date_to_timestamp(start_date),
                jh.date_to_timestamp(finish_date)
            )
            publish_status('Preparing warm-up candles…')
            _handle_warmup_candles(warmup_candles, start_date)
        except exceptions.CandlesNotFound as e:
            _handle_sync_no_candles(e, start_date, exchange, client_id=client_id, finish_date=finish_date)
        except exceptions.CandleNotFoundInDatabase as e:
            _handle_sync_no_candles(e, start_date, exchange, client_id=client_id, finish_date=finish_date)

    _raise_if_cancelled(client_id)

    if not jh.should_execute_silently():
        sync_publish('general_info', {
            'session_id': jh.get_session_id(),
            'debug_mode': str(config['app']['debug_mode']),
        })
        # candles info
        key = f"{config['app']['considering_candles'][0][0]}-{config['app']['considering_candles'][0][1]}"
        sync_publish('candles_info', stats.candles_info(candles[key]['candles']))
        # routes info
        sync_publish('routes_info', stats.routes(router.routes))

    # run backtest simulation
    result = None
    try:
        publish_status('Initializing strategies and preparing the simulation…')
        result = simulator(
            candles,
            run_silently=jh.should_execute_silently(),
            generate_csv=csv,
            generate_json=json,
            benchmark=benchmark,
            generate_hyperparameters=True,
            fast_mode=fast_mode,
        )
    except exceptions.RouteNotFound as e:
        # Extract exchange, symbol, and timeframe using regular expressions
        match = re.search(r"symbol='(.+?)', timeframe='(.+?)'", str(e))
        if match:
            symbol = match.group(1)
            timeframe = match.group(2)
            # Adjust data_routes to include the missing route
            data_routes.append({
                'exchange': exchange,
                'symbol': symbol,
                'timeframe': timeframe
            })
            # to prevent an issue with warmupcandles being None
            candles = None
            # notify the user about the missing data route and retry the backtest simulation
            sync_publish('notification', {
                'message': f'Missing data route for "{symbol}" with "{timeframe}" timeframe. Adding it and retrying...',
                'type': 'error'
            })
            # retry the backtest simulation
            _execute_backtest(
                client_id, debug_mode, user_config, exchange, routes, data_routes, start_date, finish_date, candles,
                chart, csv, json, fast_mode, benchmark, theme
            )
            return
        else:
            raise e
    except exceptions.Termination:
        raise
    except Exception as e:
        # Store exception in database (only for UI dashboard)
        if not jh.should_execute_silently():
            import traceback
            from jesse.models.BacktestSession import store_backtest_session_exception, update_backtest_session_status
            store_backtest_session_exception(
                client_id,
                f'{type(e).__name__}: {e}',
                traceback.format_exc(),
            )
            update_backtest_session_status(client_id, 'stopped')
        raise

    if result and not jh.should_execute_silently():
        _raise_if_cancelled(client_id)
        sync_publish('alert', {
            'message': f"Successfully executed backtest simulation in: {result['execution_duration']} seconds",
            'type': 'success'
        })
        sync_publish('hyperparameters', result['hyperparameters'])
        sync_publish('metrics', result['metrics'])
        sync_publish('trades', result['trades'], compression=True)

        # Generate six analytical chart images (equity_curve, drawdown, underwater,
        # monthly_heatmap, monthly_distribution, trade_pnl).
        # Must be called BEFORE store.reset() since it reads from the live store.
        publish_status('Generating performance charts…', current=100)
        _charts_folder = os.path.abspath('storage/backtest-charts')
        charts._plot_backtest_charts(
            session_id=client_id,
            charts_folder=_charts_folder,
            theme=theme,
            benchmark=benchmark,
        )
        
        # Prepare chart data if requested (call formatting functions once and cache)
        chart_data = None
        if chart:
            # Store the data for database
            chart_data = {
                'candles_chart': _get_formatted_candles_for_frontend(),
                'orders_chart': _get_formatted_orders_for_frontend(),
                'add_line_to_candle_chart': _get_add_line_to_candle_chart(),
                'add_extra_line_chart': _get_add_extra_line_chart(),
                'add_horizontal_line_to_candle_chart': _get_add_horizontal_line_to_candle_chart(),
                'add_horizontal_line_to_extra_chart': _get_add_horizontal_line_to_extra_chart()
            }
        
        # Capture strategy codes for each route
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
        
        publish_status('Saving backtest results…', current=100)
        # Update backtest session in database with results
        from jesse.models.BacktestSession import update_backtest_session_results, update_backtest_session_status
        _raise_if_cancelled(client_id)
        update_backtest_session_results(
            id=client_id,
            metrics=result.get('metrics'),
            trades=result.get('trades'),
            hyperparameters=result.get('hyperparameters'),
            chart_data=chart_data,
            execution_duration=result.get('execution_duration'),
            strategy_codes=strategy_codes if strategy_codes else None
        )
        update_backtest_session_status(client_id, 'finished')
        # Reveal results only after their charts and persisted data are both ready.
        sync_publish('progressbar', {'current': 100, 'estimated_remaining_seconds': 0, 'message': 'Backtest complete'})
        sync_publish('charts_image_ready', {'session_id': client_id})

    # close database connection
    from jesse.services.db import database
    database.close_connection()
    

def _handle_sync_no_candles(e, start_date, exchange, client_id=None, finish_date=None):
    # Prefer the structured payload the missing-candle helpers raise; only fall back
    # to parsing the message string if the symbol isn't carried on the exception.
    symbol = None
    payload = e.args[0] if getattr(e, 'args', None) else None
    if isinstance(payload, dict):
        symbol = payload.get('symbol')
    if not symbol:
        match = re.search(r"for (.*?) on (.*?)$", str(e))
        if match:
            symbol = match.group(1)

    if symbol:
        # Compute the earliest date the run actually needs (warm-up candles included)
        # so the error tells the agent/user exactly what to import to fix it.
        warmup_num = jh.get_config('env.data.warmup_candles_num', 210)
        required_start = start_date
        if warmup_num > 0:
            required_start_ts = jh.date_to_timestamp(start_date) - (
                warmup_num * jh.timeframe_to_one_minutes(jh.max_timeframe(config['app']['considering_timeframes'])) * 2 * 60_000)
            required_start = jh.timestamp_to_date(required_start_ts)

        message = (
            f"Missing candles for {symbol} on {exchange}. This run needs data from "
            f"{required_start}" + (f" to {finish_date}" if finish_date else "") +
            f" (which includes {warmup_num} warm-up candles before the start date). "
            f"Import candles for {symbol} on {exchange} starting {required_start}, then re-run."
        )

        sync_publish(
            "missing_candles",
            {
                "message": message,
                "symbol": symbol,
                "exchange": exchange,
                "start_date": required_start,
            },
        )

        # Persist a terminal error so polling clients never mistake this failed run
        # for active work.
        if client_id is not None and not jh.should_execute_silently():
            from jesse.models.BacktestSession import (
                store_backtest_session_exception,
                update_backtest_session_status,
            )
            store_backtest_session_exception(client_id, message, '')
            update_backtest_session_status(client_id, 'stopped')

        raise exceptions.CandlesNotFound({
            'message': message,
            'symbol': symbol,
            'exchange': exchange,
            'start_date': required_start,
            'finish_date': finish_date,
            'type': 'missing_candles'
        })
    raise e


def _get_formatted_candles_for_frontend():
    arr = []
    for r in router.routes:
        candles_arr = candle_service.get_candles(r.exchange, r.symbol, r.timeframe)
        # Find the index where the starting time actually begins.
        starting_index = 0
        for i, c in enumerate(candles_arr):
            if c[0] >= store.app.starting_time:
                starting_index = i
                break

        candles = [{
            'time': int(c[0]/1000),
            'open': c[1],
            'close': c[2],
            'high': c[3],
            'low': c[4],
            'volume': c[5]
        } for c in candles_arr[starting_index:]]
        arr.append({
            'exchange': r.exchange,
            'symbol': r.symbol,
            'timeframe': r.timeframe,
            'candles': candles
        })
    return arr


def _get_formatted_orders_for_frontend():
    arr = []
    for r in router.routes:
        arr.append({
            'exchange': r.exchange,
            'symbol': r.symbol,
            'timeframe': r.timeframe,
            'orders': r.strategy._executed_orders
        })
    return arr


def _get_add_line_to_candle_chart():
    arr = []
    for r in router.routes:
        arr.append({
            'exchange': r.exchange,
            'symbol': r.symbol,
            'timeframe': r.timeframe,
            'lines': r.strategy._add_line_to_candle_chart_values
        })
    return arr


def _get_add_extra_line_chart():
    arr = []
    for r in router.routes:
        arr.append({
            'exchange': r.exchange,
            'symbol': r.symbol,
            'timeframe': r.timeframe,
            'charts': r.strategy._add_extra_line_chart_values
        })
    return arr


def _get_add_horizontal_line_to_candle_chart():
    arr = []
    for r in router.routes:
        arr.append({
            'exchange': r.exchange,
            'symbol': r.symbol,
            'timeframe': r.timeframe,
            'lines': r.strategy._add_horizontal_line_to_candle_chart_values
        })
    return arr


def _get_add_horizontal_line_to_extra_chart():
    arr = []
    for r in router.routes:
        arr.append({
            'exchange': r.exchange,
            'symbol': r.symbol,
            'timeframe': r.timeframe,
            'lines': r.strategy._add_horizontal_line_to_extra_chart_values
        })
    return arr


def _handle_missing_candles(exchange: str, symbol: str, start_date: int, message: str = None):
    """Helper function to handle missing candles scenarios"""
    formatted_date = jh.timestamp_to_date(start_date)
    if message is None:
        message = f'Missing trading candles for {symbol} on {exchange} from {formatted_date}'
    
    sync_publish(
        "missing_candles",
        {
            "message": message,
            "symbol": symbol,
            "exchange": exchange,
            "start_date": formatted_date,
        },
    )
    
    raise exceptions.CandlesNotFound({
        'message': message,
        'symbol': symbol,
        'exchange': exchange,
        'start_date': start_date,
        'type': 'missing_candles'
    })


def load_candles(start_date: int, finish_date: int) -> Tuple[dict, dict]:
    warmup_num = jh.get_config('env.data.warmup_candles_num', 210)
    max_timeframe = jh.max_timeframe(config['app']['considering_timeframes'])

    # load and add required warm-up candles for backtest, and then Prepare trading candles
    trading_candles = {}
    warmup_candles = {}
    for c in config['app']['considering_candles']:
        exchange, symbol = c[0], c[1]
        if jh.app_mode() == 'backtest' and not jh.should_execute_silently():
            publish_status(f'Loading historical candles for {symbol} on {exchange}…')
        warmup_candles_arr, trading_candle_arr = candle_service.get_candles_from_db(
            exchange, symbol, max_timeframe, start_date, finish_date, warmup_num, caching=True, is_for_jesse=True
        )

        # Ensure that trading_candle_arr is not None or empty
        if trading_candle_arr is None or (isinstance(trading_candle_arr, np.ndarray) and trading_candle_arr.size == 0):
            _handle_missing_candles(
                exchange, 
                symbol, 
                start_date, 
                f"Missing trading candles for {symbol} on {exchange}"
            )

        try:
            candle_service.validate_observed_one_minute_candles(trading_candle_arr, exchange, symbol)
        except ValueError as exc:
            _handle_missing_candles(exchange, symbol, start_date, str(exc))
        if not _supports_observed_timestamp_replay_scope() and (
            trading_candle_arr[0, 0] > start_date
            or trading_candle_arr[-1, 0] < finish_date - 60_000
        ):
            _handle_missing_candles(exchange, symbol, start_date)

        # add trading candles
        trading_candles[jh.key(exchange, symbol)] = {
            'exchange': exchange,
            'symbol': symbol,
            'candles': trading_candle_arr
        }

        warmup_candles[jh.key(exchange, symbol)] = {
            'exchange': exchange,
            'symbol': symbol,
            'candles': warmup_candles_arr
        }

    return warmup_candles, trading_candles


def _handle_warmup_candles(warmup_candles: dict, start_date: str) -> None:
    try:
        store.candles.uses_timestamp_buckets = _supports_observed_timestamp_replay_scope()
        store.candles.enforce_warmup = True
        for c in config['app']['considering_candles']:
            exchange, symbol = c[0], c[1]
            candle_array = warmup_candles[jh.key(exchange, symbol)]['candles']
            candle_service.validate_observed_one_minute_candles(candle_array, exchange, symbol)
            candle_service.inject_warmup_candles_to_store(
                candle_array,
                exchange,
                symbol,
                available_at=jh.date_to_timestamp(start_date),
            )
    except ValueError as e:
        # This date is an import suggestion; sparse warmup counts completed observed buckets.
        warmup_num = jh.get_config('env.data.warmup_candles_num', 210)
        max_timeframe = jh.max_timeframe(config['app']['considering_timeframes'])
        warmup_minutes = TIMEFRAME_TO_ONE_MINUTES[max_timeframe] * warmup_num
        warmup_start_timestamp = jh.date_to_timestamp(start_date) - (warmup_minutes * 60_000)
        warmup_start_date = jh.timestamp_to_date(warmup_start_timestamp)
        sync_publish(
            "missing_candles",
            {
                "message": f'Missing warmup candles for {symbol} on {exchange} from {warmup_start_date}',
                "symbol": symbol,
                "exchange": exchange,
                "start_date": warmup_start_date,
            },
        )
        raise exceptions.CandlesNotFound(str(e))


def simulator(*args, fast_mode: bool = False, **kwargs) -> dict:
    candles = args[0] if args else kwargs['candles']
    uses_timestamp_replay = _uses_observed_timestamp_replay(candles)
    store.candles.uses_timestamp_buckets = uses_timestamp_replay
    if uses_timestamp_replay:
        if fast_mode:
            return _skip_simulator(*args, **kwargs)
        return _timestamp_simulator(*args, fast_mode=False, **kwargs)
    if fast_mode:
        return _skip_simulator(*args, **kwargs)

    return _step_simulator(*args, **kwargs)


def _uses_observed_timestamp_replay(candles: dict) -> bool:
    """Use timestamp replay only when source rows cannot share the dense minute index.

    The legacy simulators are substantially faster for contiguous, aligned crypto data and have
    identical event boundaries in that case. Real gaps or unequal instrument timelines require the
    timestamp engine so absent rows remain absent and same-time updates stay atomic.
    """
    reference_timestamps = None
    for candle_data in candles.values():
        timestamps = candle_data['candles'][:, 0]
        if len(timestamps) > 1 and not (np.diff(timestamps) == 60_000).all():
            return True
        if reference_timestamps is None:
            reference_timestamps = timestamps
        elif not np.array_equal(timestamps, reference_timestamps):
            return True
    return False


def _supports_observed_timestamp_replay_scope() -> bool:
    return bool(config['app']['considering_candles'] and router.routes)


def _timestamp_replay_common_start(candles: dict) -> int:
    """Return one source timestamp after every route has its required warmup."""
    if not candles:
        raise ValueError('At least one observed candle series is required.')
    common_start = max(int(candle_data['candles'][0, 0]) for candle_data in candles.values())
    required_warmup = (
        jh.get_config('env.data.warmup_candles_num', 0)
        if store.candles.enforce_warmup
        else 0
    )
    for route in router.routes + router.data_routes:
        completed_count = len(store.candles.get_storage(
            route.exchange,
            route.symbol,
            route.timeframe,
        ))
        deficit = required_warmup - completed_count
        if deficit <= 0:
            continue
        key = jh.key(route.exchange, route.symbol)
        candle_array = candles[key]['candles']
        timeframe_ms = TIMEFRAME_TO_ONE_MINUTES[route.timeframe] * 60_000
        bucket_starts = np.unique(
            (candle_array[:, 0].astype(np.int64) // timeframe_ms) * timeframe_ms
        )
        if len(bucket_starts) <= deficit:
            raise exceptions.CandlesNotFound(
                f'{route.symbol} on {route.exchange} does not contain {required_warmup} completed '
                f'{route.timeframe} warmup candles followed by at least one trading candle.'
            )
        common_start = max(common_start, int(bucket_starts[deficit - 1]) + timeframe_ms)

    for candle_data in candles.values():
        if not (candle_data['candles'][:, 0] >= common_start).any():
            raise exceptions.CandlesNotFound(
                f"No trading candle remains for {candle_data['symbol']} on {candle_data['exchange']} "
                f'after the common warmup boundary {jh.timestamp_to_time(common_start)}.'
            )
    return common_start


def _timestamp_bucket_generation_schedule(
        candles: np.ndarray,
        generating_timeframes: list[tuple[str, int]],
) -> dict[int, list[tuple[str, int]]]:
    """Map each completed nonempty clock bucket to its first observed availability event."""
    schedule: dict[int, list[tuple[str, int]]] = {}
    event_times = candles[:, 0].astype(np.int64) + 60_000
    timestamps = candles[:, 0].astype(np.int64)
    for timeframe, timeframe_minutes in generating_timeframes:
        timeframe_ms = timeframe_minutes * 60_000
        bucket_starts = (timestamps // timeframe_ms) * timeframe_ms
        boundaries = np.flatnonzero(np.diff(bucket_starts)) + 1
        starts = np.concatenate(([0], boundaries))
        for start in starts:
            bucket_end = int(bucket_starts[start]) + timeframe_ms
            release_index = int(np.searchsorted(event_times, bucket_end, side='left'))
            if release_index < len(candles):
                schedule.setdefault(release_index, []).append(
                    (timeframe, int(start))
                )
    return schedule


def _build_timestamp_replay_plan(
        candles: dict,
        generating_timeframes: list[tuple[str, int]],
) -> tuple[int, list[dict]]:
    """Merge unequal source streams and aggregate releases into ordered availability events."""
    common_start = _timestamp_replay_common_start(candles)
    events: dict[int, dict] = {}
    for key in sorted(candles):
        candle_array = candles[key]['candles']
        timestamps = candle_array[:, 0].astype(np.int64)
        first_trading_index = int(np.searchsorted(timestamps, common_start, side='left'))
        for index in range(first_trading_index, len(candle_array)):
            event_time = int(timestamps[index]) + 60_000
            event = events.setdefault(event_time, {
                'time': event_time,
                'sources': [],
                'aggregates': [],
            })
            event['sources'].append((key, index))

        schedule = _timestamp_bucket_generation_schedule(candle_array, generating_timeframes)
        for release_index, updates in schedule.items():
            if release_index < first_trading_index:
                continue
            event_time = int(timestamps[release_index]) + 60_000
            event = events.setdefault(event_time, {
                'time': event_time,
                'sources': [],
                'aggregates': [],
            })
            event['aggregates'].extend(
                (key, timeframe, start)
                for timeframe, start in updates
            )

    ordered_events = [events[event_time] for event_time in sorted(events)]
    for event in ordered_events:
        event['sources'].sort()
        event['aggregates'].sort()
    return common_start, ordered_events


def _prepare_timestamp_replay_warmup(candles: dict, common_start: int) -> None:
    """Move pre-common source rows into warmup and enforce one shared safe start."""
    for key in sorted(candles):
        candle_data = candles[key]
        exchange, symbol = candle_data['exchange'], candle_data['symbol']
        candle_array = candle_data['candles']
        pre_start = candle_array[candle_array[:, 0] < common_start]
        if len(pre_start):
            candle_service.batch_add_candle(
                pre_start,
                exchange,
                symbol,
                timeframes.MINUTE_1,
                with_generation=False,
            )

        visible_source = candle_service.get_candles(exchange, symbol, timeframes.MINUTE_1)
        if len(visible_source) == 0:
            continue
        for timeframe in config['app']['considering_timeframes']:
            if timeframe == timeframes.MINUTE_1:
                continue
            generated = candle_service.generate_completed_candles_from_observed_minutes(
                timeframe,
                visible_source,
                common_start,
            )
            candle_service.batch_add_candle(
                generated,
                exchange,
                symbol,
                timeframe,
                with_generation=False,
            )

    required_warmup = (
        jh.get_config('env.data.warmup_candles_num', 0)
        if store.candles.enforce_warmup
        else 0
    )
    if required_warmup <= 0:
        return
    for route in router.routes + router.data_routes:
        completed_count = len(store.candles.get_storage(
            route.exchange,
            route.symbol,
            route.timeframe,
        ))
        if completed_count < required_warmup:
            raise exceptions.CandlesNotFound(
                f'Only {completed_count} of {required_warmup} required completed {route.timeframe} '
                f'warmup candles are available for {route.symbol} on {route.exchange} before '
                f'{jh.timestamp_to_time(common_start)}.'
            )


def _apply_timestamp_replay_event(
        event: dict,
        candles: dict,
        candles_pipelines: Dict[str, BaseCandlesPipeline | None],
        process_orders: bool,
) -> tuple[set[tuple[str, str, str]], set[tuple[str, str]]]:
    """Atomically expose one union event and return its exact updates and real source pairs."""
    # Historical trade timestamps are floats because candle arrays are float64;
    # retain that public result shape while event-plan keys stay exact integers.
    store.app.time = float(event['time'])
    source_updates = []
    for key, index in event['sources']:
        candle_data = candles[key]
        candle_array = candle_data['candles']
        candles_pipeline = candles_pipelines[key]
        if candles_pipeline is None:
            source_candle = candle_array[index]
        else:
            source_candle = candles_pipeline.get_candles(
                candle_array[index:index + candles_pipeline._batch_size],
                index,
                -1,
            )
            candle_array[index] = source_candle
        exchange, symbol = candle_data['exchange'], candle_data['symbol']
        source_storage = store.candles.get_storage(exchange, symbol, timeframes.MINUTE_1)
        previous_close = source_storage[-1][2] if len(source_storage) else None
        source_updates.append((key, exchange, symbol, source_candle, previous_close))

    updated_routes: set[tuple[str, str, str]] = set()
    source_pairs: set[tuple[str, str]] = set()
    for _, exchange, symbol, source_candle, previous_close in source_updates:
        candle_service.add_candle(
            source_candle,
            exchange,
            symbol,
            timeframes.MINUTE_1,
            with_execution=False,
            with_generation=False,
        )
        updated_routes.add((exchange, symbol, timeframes.MINUTE_1))
        source_pairs.add((exchange, symbol))

    aggregates_by_key: dict[str, list[tuple[str, int]]] = {}
    for key, timeframe, start in event['aggregates']:
        aggregates_by_key.setdefault(key, []).append((timeframe, start))

    # Every source row is visible before price effects begin. Within each
    # instrument, preserve the dense simulator's price-before-aggregate order.
    for key, exchange, symbol, source_candle, previous_close in source_updates:
        if process_orders:
            _simulate_price_change_effect(
                source_candle,
                exchange,
                symbol,
                previous_close=previous_close,
            )

        for timeframe, start in aggregates_by_key.pop(key, []):
            timeframe_ms = TIMEFRAME_TO_ONE_MINUTES[timeframe] * 60_000
            bucket_start = int(candles[key]['candles'][start, 0])
            bucket_start -= bucket_start % timeframe_ms
            visible_source = candle_service.get_candles(exchange, symbol, timeframes.MINUTE_1)
            source_start = int(np.searchsorted(visible_source[:, 0], bucket_start, side='left'))
            source_stop = int(np.searchsorted(
                visible_source[:, 0],
                bucket_start + timeframe_ms,
                side='left',
            ))
            generated = candle_service.generate_candle_from_observed_minutes(
                timeframe,
                visible_source[source_start:source_stop],
            )
            candle_service.add_candle(
                generated,
                exchange,
                symbol,
                timeframe,
                with_execution=False,
                with_generation=False,
            )
            available_at = int(generated[0]) + timeframe_ms
            if available_at == event['time']:
                updated_routes.add((exchange, symbol, timeframe))

    return updated_routes, source_pairs


def _timestamp_event_updates_trading_route(
        event: dict,
        candles: dict,
        trading_routes: set[tuple[str, str, str]],
) -> bool:
    """Return whether an event makes at least one strategy route executable."""
    for key, _ in event['sources']:
        candle_data = candles[key]
        if (candle_data['exchange'], candle_data['symbol'], timeframes.MINUTE_1) in trading_routes:
            return True
    for key, timeframe, _ in event['aggregates']:
        candle_data = candles[key]
        if (candle_data['exchange'], candle_data['symbol'], timeframe) in trading_routes:
            return True
    return False


def _apply_timestamp_replay_batch(
        events: list[dict],
        candles: dict,
) -> tuple[set[tuple[str, str, str]], set[tuple[str, str]]]:
    """Publish a side-effect-free span at once while preserving its final event boundary.

    The caller permits this only without orders, open positions, or candle pipelines, so skipped
    intermediate events cannot execute user code, transform prices, fill orders, or liquidate.
    """
    endpoint = events[-1]
    source_indices: dict[str, list[int]] = {}
    for event in events:
        for key, index in event['sources']:
            source_indices.setdefault(key, []).append(index)

    for key, indices in source_indices.items():
        candle_data = candles[key]
        exchange, symbol = candle_data['exchange'], candle_data['symbol']
        source_rows = candle_data['candles'][indices]
        store.candles.get_storage(exchange, symbol, timeframes.MINUTE_1).append_multiple(source_rows)
        position = store.positions.get_position(exchange, symbol)
        if position is not None:
            position.current_price = source_rows[-1, 2]

    updated_routes: set[tuple[str, str, str]] = set()
    source_pairs: set[tuple[str, str]] = set()
    for key, _ in endpoint['sources']:
        candle_data = candles[key]
        exchange, symbol = candle_data['exchange'], candle_data['symbol']
        updated_routes.add((exchange, symbol, timeframes.MINUTE_1))
        source_pairs.add((exchange, symbol))

    for event in events:
        for key, timeframe, start in event['aggregates']:
            candle_data = candles[key]
            exchange, symbol = candle_data['exchange'], candle_data['symbol']
            timeframe_ms = TIMEFRAME_TO_ONE_MINUTES[timeframe] * 60_000
            bucket_start = int(candle_data['candles'][start, 0])
            bucket_start -= bucket_start % timeframe_ms
            visible_source = candle_service.get_candles(exchange, symbol, timeframes.MINUTE_1)
            source_start = int(np.searchsorted(visible_source[:, 0], bucket_start, side='left'))
            source_stop = int(np.searchsorted(
                visible_source[:, 0],
                bucket_start + timeframe_ms,
                side='left',
            ))
            generated = candle_service.generate_candle_from_observed_minutes(
                timeframe,
                visible_source[source_start:source_stop],
            )
            candle_service.add_candle(
                generated,
                exchange,
                symbol,
                timeframe,
                with_execution=False,
                with_generation=False,
            )
            if event is endpoint and int(generated[0]) + timeframe_ms == endpoint['time']:
                updated_routes.add((exchange, symbol, timeframe))

    store.app.time = float(endpoint['time'])
    return updated_routes, source_pairs


def _timestamp_simulator(
        candles: dict,
        run_silently: bool,
        fast_mode: bool = False,
        hyperparameters: dict = None,
        generate_csv: bool = False,
        generate_json: bool = False,
        generate_equity_curve: bool = False,
        benchmark: bool = False,
        generate_hyperparameters: bool = False,
        generate_logs: bool = False,
        with_candles_pipeline: bool = True,
        candles_pipeline_class = None,
        candles_pipeline_kwargs: dict = None,
) -> dict:
    """Replay dense or sparse instruments through one union of availability timestamps."""
    if generate_logs:
        config['app']['debug_mode'] = True
    begin_time_track = time.time()
    generating_timeframes = [
        (timeframe, TIMEFRAME_TO_ONE_MINUTES[timeframe])
        for timeframe in config['app']['considering_timeframes']
        if timeframe != timeframes.MINUTE_1
    ]
    common_start, events = _build_timestamp_replay_plan(candles, generating_timeframes)
    candles_pipelines = _prepare_routes(
        hyperparameters=hyperparameters,
        with_candles_pipeline=with_candles_pipeline,
        candles_pipeline_class=candles_pipeline_class,
        candles_pipeline_kwargs=candles_pipeline_kwargs,
    )
    _prepare_timestamp_replay_warmup(candles, common_start)
    store.app.starting_time = common_start
    store.app.time = common_start

    save_daily_portfolio_balance(is_initial=True)
    # Preserve Jesse's historical first sample after the first 1,440 source
    # minutes, then keep a fixed daily schedule across market closures.
    next_balance_sample_time = common_start + 86_460_000
    balance_sample_cadence = (
        _calculate_minimum_candle_step() * 60_000
        if fast_mode
        else 60_000
    )
    progressbar = Progressbar(len(events), step=420)
    last_update_time = None
    routes_info = sorted(
        router.routes,
        key=lambda route: (route.exchange, route.symbol, route.timeframe, str(route.strategy_name)),
    )
    trading_routes = {
        (route.exchange, route.symbol, route.timeframe)
        for route in routes_info
    }
    can_batch_source_rows = fast_mode and all(pipeline is None for pipeline in candles_pipelines.values())

    event_index = 0
    while event_index < len(events):
        event = events[event_index]
        batch_end = event_index
        if (
            can_batch_source_rows
            and store.orders.count_all_active_orders() == 0
            and store.positions.count_open_positions() == 0
        ):
            while batch_end < len(events) - 1:
                if _timestamp_event_updates_trading_route(events[batch_end], candles, trading_routes):
                    break
                event_time = int(events[batch_end]['time'])
                is_balance_sample_event = (
                    event_time >= next_balance_sample_time
                    and (event_time - common_start) % balance_sample_cadence == 0
                )
                if is_balance_sample_event:
                    break
                batch_end += 1

        if batch_end > event_index:
            updated_routes, source_pairs = _apply_timestamp_replay_batch(
                events[event_index:batch_end + 1],
                candles,
            )
            event = events[batch_end]
        else:
            updated_routes, source_pairs = _apply_timestamp_replay_event(
                event,
                candles,
                candles_pipelines,
                process_orders=True,
            )
        if not run_silently:
            last_update_time = _update_progress_bar(
                progressbar,
                run_silently,
                batch_end,
                candle_step=420,
                last_update_time=last_update_time,
            )

        for route in routes_info:
            if (route.exchange, route.symbol, route.timeframe) in updated_routes:
                route.strategy._execute()
        for exchange, symbol in sorted(source_pairs):
            order_service.update_active_orders(exchange, symbol)
        order_service.execute_simulated_market_orders()

        # Fast requests historically sampled equity only at skip boundaries.
        # Keep that result compatibility while decisions retain exact timestamp boundaries.
        is_balance_sample_event = (
            (int(store.app.time) - common_start) % balance_sample_cadence == 0
        )
        if int(store.app.time) >= next_balance_sample_time and is_balance_sample_event:
            save_daily_portfolio_balance()
            while next_balance_sample_time <= int(store.app.time):
                next_balance_sample_time += 86_400_000

        event_index = batch_end + 1

    _finish_progress_bar(progressbar, run_silently)
    execution_duration = 0
    if not run_silently:
        execution_duration = round(time.time() - begin_time_track, 2)

    for route in routes_info:
        route.strategy._terminate()
        order_service.execute_simulated_market_orders()
    save_daily_portfolio_balance()
    store.app.ending_time = store.app.time + 60_000

    result = _generate_outputs(
        candles,
        generate_csv=generate_csv,
        generate_json=generate_json,
        generate_equity_curve=generate_equity_curve,
        benchmark=benchmark,
        generate_hyperparameters=generate_hyperparameters,
        generate_logs=generate_logs,
    )
    result['execution_duration'] = execution_duration
    return result


def _step_simulator(
        candles: dict,
        run_silently: bool,
        hyperparameters: dict = None,
        generate_csv: bool = False,
        generate_json: bool = False,
        generate_equity_curve: bool = False,
        benchmark: bool = False,
        generate_hyperparameters: bool = False,
        generate_logs: bool = False,
        with_candles_pipeline: bool = True,
        candles_pipeline_class = None,
        candles_pipeline_kwargs: dict = None,
) -> dict:
    # In case generating logs is specifically demanded, the debug mode must be enabled.
    if generate_logs:
        config['app']['debug_mode'] = True

    begin_time_track = time.time()

    key = f"{config['app']['considering_candles'][0][0]}-{config['app']['considering_candles'][0][1]}"
    first_candles_set = candles[key]['candles']

    length = _simulation_minutes_length(candles)
    _prepare_times_before_simulation(candles)
    candles_pipelines = _prepare_routes(
        hyperparameters=hyperparameters,
        with_candles_pipeline=with_candles_pipeline,
        candles_pipeline_class=candles_pipeline_class,
        candles_pipeline_kwargs=candles_pipeline_kwargs
    )

    # add initial balance
    save_daily_portfolio_balance(is_initial=True)
    # Preserve Jesse's historical first sample after row 1,440, then keep a
    # fixed daily schedule so delayed sparse rows do not shift later samples.
    next_balance_sample_time = int(store.app.time) + 86_460_000

    progressbar = Progressbar(length, step=420)
    last_update_time = None

    # hoist loop-invariant lookups out of the per-minute hot loop
    candles_info = [
        (candles[j]['candles'], candles_pipelines[j], candles[j]['exchange'], candles[j]['symbol'])
        for j in candles
    ]
    # bigger timeframes to generate (1m needs no work)
    generating_timeframes = [
        (timeframe, TIMEFRAME_TO_ONE_MINUTES[timeframe])
        for timeframe in config['app']['considering_timeframes']
        if timeframe != timeframes.MINUTE_1
    ]
    timestamp_generation_schedule = (
        _timestamp_bucket_generation_schedule(first_candles_set, generating_timeframes)
        if store.candles.uses_timestamp_buckets
        else {}
    )
    routes_info = [
        (r, TIMEFRAME_TO_ONE_MINUTES[r.timeframe], r.strategy, r.exchange, r.symbol)
        for r in router.routes
    ]
    print_shorter_period_candles = jh.is_debuggable('shorter_period_candles')
    print_trading_candles = jh.is_debuggable('trading_candles')
    store_app = store.app
    add_candle = candle_service.add_candle
    generate_candle_from_one_minutes = candle_service.generate_candle_from_one_minutes
    update_active_orders = order_service.update_active_orders
    execute_simulated_market_orders = order_service.execute_simulated_market_orders

    # Pipeline-free, ascending float64 candles can be copied into storage once;
    # each observed event then advances the visible storage index.
    prefilled = []
    for candles_arr, candles_pipeline, exchange, symbol in candles_info:
        arr_1m = None
        if (
            # pipelines rewrite candles batch-by-batch — can't precompute
            candles_pipeline is None
            # the storage buffer uses float64 rows
            and candles_arr.dtype == np.float64
            and candles_arr.flags.writeable
            # the loop below indexes every observed row in the series
            and len(candles_arr) == length
            # a zero timestamp takes add_candle's special debug/return path
            and not (candles_arr[:, 0] == 0).any()
            # strictly increasing timestamps guarantee every per-minute
            # add_candle would have hit its plain-append branch (never the
            # update/backfill branches), which is all an index bump replicates
            and (length < 2 or (np.diff(candles_arr[:, 0]) > 0).all())
        ):
            storage = store.candles.get_storage(exchange, symbol, '1m')
            base = storage.index + 1
            # Prefill is safe only when the series follows any warmup rows.
            if base == 0 or candles_arr[0, 0] > storage.array[base - 1, 0]:
                needed = base + length
                if needed > len(storage.array):
                    # Allocate enough room for the complete simulation range.
                    new_array = np.zeros((needed,) + storage.array.shape[1:], dtype=storage.array.dtype)
                    new_array[:base] = storage.array[:base]
                    storage.array = new_array
                storage.array[base:base + length] = candles_arr
                arr_1m = storage
        prefilled.append(arr_1m)
    candles_info = [info + (prefilled[idx],) for idx, info in enumerate(candles_info)]

    for i in range(length):
        # update time
        store_app.time = first_candles_set[i, 0] + 60_000
        i_next = i + 1

        updated_timeframes = {timeframes.MINUTE_1}

        # add candles
        for candles_arr, candles_pipeline, exchange, symbol, arr_1m in candles_info:
            if arr_1m is not None:
                # The candle is already copied into the storage buffer, so
                # exposing this observed candle only requires an index advance.
                short_candle = candles_arr[i]
                arr_1m.index += 1
            else:
                if candles_pipeline is None:
                    short_candle = candles_arr[i]
                else:
                    short_candle = candles_pipeline.get_candles(
                        candles_arr[i: i + candles_pipeline._batch_size], i, -1
                    )

                # Pipeline output becomes the canonical row used by storage and
                # higher-timeframe generation for this simulation.
                candles_arr[i] = short_candle

                add_candle(short_candle, exchange, symbol, '1m', with_execution=False,
                           with_generation=False)

            # print short candle
            if print_shorter_period_candles:
                candle_service.print_candle(short_candle, True, symbol)

            previous_close = candles_arr[i - 1, 2] if i != 0 else None
            _simulate_price_change_effect(
                short_candle,
                exchange,
                symbol,
                previous_close=previous_close,
            )

            # Timestamp replay publishes every completed clock bucket at the
            # first real source-candle event on or after that bucket's boundary.
            if store.candles.uses_timestamp_buckets:
                for timeframe, start in timestamp_generation_schedule.get(i, []):
                    timeframe_ms = TIMEFRAME_TO_ONE_MINUTES[timeframe] * 60_000
                    bucket_start = int(candles_arr[start, 0])
                    bucket_start -= bucket_start % timeframe_ms
                    visible_source = candle_service.get_candles(exchange, symbol, timeframes.MINUTE_1)
                    source_start = int(np.searchsorted(visible_source[:, 0], bucket_start, side='left'))
                    source_stop = int(np.searchsorted(
                        visible_source[:, 0], bucket_start + timeframe_ms, side='left'
                    ))
                    generated_candle = candle_service.generate_candle_from_observed_minutes(
                        timeframe,
                        visible_source[source_start:source_stop],
                    )
                    add_candle(
                        generated_candle,
                        exchange,
                        symbol,
                        timeframe,
                        with_execution=False,
                        with_generation=False,
                    )
                    # A bucket crossed during a closure becomes visible when the
                    # market resumes, but it cannot create a delayed strategy
                    # callback pretending that its absent boundary had traded.
                    if int(generated_candle[0]) + timeframe_ms == int(store_app.time):
                        updated_timeframes.add(timeframe)
            else:
                for timeframe, count in generating_timeframes:
                    if i_next % count != 0:
                        continue
                    generated_candle = generate_candle_from_one_minutes(
                        timeframe,
                        candles_arr[(i_next - count):i_next]
                    )

                    add_candle(
                        generated_candle,
                        exchange,
                        symbol,
                        timeframe,
                        with_execution=False,
                        with_generation=False
                    )

        # when run_silently, _update_progress_bar is a no-op that still paid
        # for a call + time.time() every minute — skip it entirely
        if not run_silently:
            last_update_time = _update_progress_bar(progressbar, run_silently, i, candle_step=420,
                                                    last_update_time=last_update_time)

        # now that all new generated candles are ready, execute
        for r, count, strategy, exchange, symbol in routes_info:
            if store.candles.uses_timestamp_buckets:
                if r.timeframe in updated_timeframes:
                    strategy._execute()
            # 1m timeframe
            elif count == 1:
                strategy._execute()
            elif i_next % count == 0:
                # print candle
                if print_trading_candles:
                    candle_service.print_candle(candle_service.get_current_candle(exchange, symbol, r.timeframe), False,
                                 symbol)
                strategy._execute()

            update_active_orders(exchange, symbol)

        # now check to see if there's any MARKET orders waiting to be executed
        execute_simulated_market_orders()

        # Timestamp-based sampling keeps sparse market closures as real gaps
        # instead of treating 1,440 available rows as one calendar day.
        if int(store_app.time) >= next_balance_sample_time:
            save_daily_portfolio_balance()
            while next_balance_sample_time <= int(store_app.time):
                next_balance_sample_time += 86_400_000

    _finish_progress_bar(progressbar, run_silently)

    execution_duration = 0
    if not run_silently:
        # print executed time for the backtest session
        finish_time_track = time.time()
        execution_duration = round(finish_time_track - begin_time_track, 2)

    for r in router.routes:
        r.strategy._terminate()
        order_service.execute_simulated_market_orders()

    # now that backtest simulation is finished, add finishing balance
    save_daily_portfolio_balance()

    # set the ending time for the backtest session
    store.app.ending_time = store.app.time + 60_000

    result = _generate_outputs(
        candles,
        generate_csv=generate_csv,
        generate_json=generate_json,
        generate_equity_curve=generate_equity_curve,
        benchmark=benchmark,
        generate_hyperparameters=generate_hyperparameters,
        generate_logs=generate_logs,
    )
    result['execution_duration'] = execution_duration
    return result


def _simulation_minutes_length(candles: dict) -> int:
    key = f"{config['app']['considering_candles'][0][0]}-{config['app']['considering_candles'][0][1]}"
    first_candles_set = candles[key]["candles"]
    return len(first_candles_set)


def _prepare_times_before_simulation(candles: dict) -> None:
    # result = {}
    # begin_time_track = time.time()
    key = f"{config['app']['considering_candles'][0][0]}-{config['app']['considering_candles'][0][1]}"
    first_candles_set = candles[key]["candles"]
    # length = len(first_candles_set)
    # to preset the array size for performance
    try:
        store.app.starting_time = first_candles_set[0][0]
    except IndexError:
        raise IndexError('Check your "warm_up_candles" config value')
    store.app.time = first_candles_set[0][0]


def _prepare_routes(
                    hyperparameters: dict = None,
                    with_candles_pipeline: bool = True,
                    candles_pipeline_class = None,
                    candles_pipeline_kwargs: dict = None,
                    ) -> Dict[str, BaseCandlesPipeline | None]:
    # initiate strategies
    candles_pipeline = {}

    for r in router.routes:
        # if the r.strategy is str read it from file
        if isinstance(r.strategy_name, str):
            StrategyClass = jh.get_strategy_class(r.strategy_name)
        # else it is a class object so just use it
        else:
            StrategyClass = r.strategy_name

        try:
            r.strategy = StrategyClass()
        except TypeError:
            raise exceptions.InvalidStrategy(
                "Strategy validation failed. Make sure your strategy has the mandatory methods such as should_long(), "
                "go_long(), etc. For working examples, visit: https://jesse.trade/strategies"
            )
        except:
            raise

        r.strategy.name = r.strategy_name
        r.strategy.exchange = r.exchange
        r.strategy.symbol = r.symbol
        r.strategy.timeframe = r.timeframe

        # Determine hyperparameters for this specific route.
        # External hyperparameters (passed from optimize mode) take priority;
        # otherwise fall back to the route's own DNA string.
        # A per-route local variable is used so the loop never leaks one
        # strategy's decoded HP into the next strategy.
        route_hp = hyperparameters
        if route_hp is None and len(r.strategy.dna()) > 0:
            route_hp = jh.dna_to_hp(
                r.strategy.hyperparameters(), r.strategy.dna()
            )

        # inject hyperparameters sent within the optimize mode
        if route_hp is not None:
            r.strategy.hp = route_hp

        # init few objects that couldn't be initiated in Strategy __init__
        # it also injects hyperparameters into self.hp in case the route does not uses any DNAs
        r.strategy._init_objects()

        # monte-carlo simulation
        if with_candles_pipeline:
            if candles_pipeline_class is not None:
                # Use the provided pipeline class with kwargs if available
                kwargs = candles_pipeline_kwargs or {}
                candles_pipeline[jh.key(r.exchange, r.symbol)] = candles_pipeline_class(**kwargs)
            else:
                # Otherwise, fall back to the strategy's pipeline
                candles_pipeline[jh.key(r.exchange, r.symbol)] = r.strategy.candles_pipeline()
        else: # normal backtest
            candles_pipeline[jh.key(r.exchange, r.symbol)] = None

        store.positions.get_position(r.exchange, r.symbol).strategy = r.strategy

    # Ensure pipelines exist for data routes as well (no strategy attached)
    # Keys in `candles` include both trading and data routes; provide a pipeline (or None) for each
    for dr in getattr(router, 'data_routes', []) or []:
        key = jh.key(dr.exchange, dr.symbol)
        if key in candles_pipeline:
            continue
        if with_candles_pipeline and candles_pipeline_class is not None:
            kwargs = candles_pipeline_kwargs or {}
            candles_pipeline[key] = candles_pipeline_class(**kwargs)
        else:
            candles_pipeline[key] = None

    return candles_pipeline


def get_candles_from_pipeline(candles_pipeline: Optional[BaseCandlesPipeline], candles: np.ndarray, i: int, candles_step: int = -1) -> np.ndarray:
    if candles_pipeline is None:
        if candles_step == -1:
            return candles[i]
        else:
            return candles[i: i+candles_step]
    return candles_pipeline.get_candles(candles[i: i + candles_pipeline._batch_size], i, candles_step)


def _update_progress_bar(
        progressbar: Progressbar, run_silently: bool, candle_index: int, candle_step: int, last_update_time: float
) -> float:
    if run_silently:
        return last_update_time

    # candle_index is the last processed row/event, not the number of loop calls.
    # Fast sparse batches can skip exact multiples of the reporting step.
    completed = min(candle_index + 1, progressbar.length)
    advance = completed - progressbar.index
    if advance >= candle_step or (advance > 0 and completed == progressbar.length):
        progressbar.update(advance)

    current_time = time.time()
    # Cancellation and progress use the shared coordinator; twice per second keeps
    # the dashboard responsive without making transport cost scale with candle count.
    if last_update_time is None or (current_time - last_update_time) >= 0.5:
        _raise_if_cancelled(jh.get_session_id())
        sync_publish(
            "progressbar",
            {
                "message": "Simulating historical candles…",
                "current": progressbar.current,
                "estimated_remaining_seconds": progressbar.estimated_remaining_seconds,
            },
        )
        last_update_time = current_time

    return last_update_time


def _finish_progress_bar(progressbar: Progressbar, run_silently: bool):
    if run_silently:
        return

    progressbar.finish()
    publish_status('Calculating performance metrics…', current=100)


def _order_is_crossed_by_opening_gap(
        order: Order,
        previous_close: float,
        open_price: float,
) -> bool:
    """Return whether a resting limit or stop order became marketable at the open."""
    if not order.is_active:
        return False

    order_price = order.price
    if order_price is None:
        return False

    return _priced_order_is_crossed_by_opening_gap(
        order,
        order_price,
        previous_close,
        open_price,
    )


def _priced_order_is_crossed_by_opening_gap(
        order: Order,
        order_price: float,
        previous_close: float,
        open_price: float,
) -> bool:
    """Check a known-active, priced order against one close-to-open transition."""
    if open_price > previous_close:
        if not previous_close <= order_price <= open_price:
            return False
        return (
            (order.type == order_types.LIMIT and order.side == sides.SELL)
            or (order.type == order_types.STOP and order.side == sides.BUY)
        )
    if open_price < previous_close:
        if not open_price <= order_price <= previous_close:
            return False
        return (
            (order.type == order_types.LIMIT and order.side == sides.BUY)
            or (order.type == order_types.STOP and order.side == sides.SELL)
        )
    return False


def _get_opening_gap_orders(
        previous_close: Optional[float],
        candle: np.ndarray,
        exchange: str,
        symbol: str,
        active_orders: Optional[List[Order]] = None,
) -> List[Order]:
    """Return pre-existing orders crossed between the previous close and current open."""
    open_price = candle[1]
    if previous_close is None or previous_close == open_price:
        return []

    if active_orders is None:
        active_orders = store.orders.get_active_orders(exchange, symbol)

    crossed_orders = [
        order
        for order in active_orders
        if _order_is_crossed_by_opening_gap(order, previous_close, open_price)
    ]
    if len(crossed_orders) > 1:
        crossed_orders.sort(key=lambda order: order.price, reverse=open_price < previous_close)
    return crossed_orders


def _execute_opening_gap_orders(
        previous_close: Optional[float],
        candle: np.ndarray,
        exchange: str,
        symbol: str,
        active_orders: Optional[List[Order]] = None,
        opening_gap_orders: Optional[List[Order]] = None,
) -> bool:
    """Execute crossed resting orders at the first available opening price."""
    orders = opening_gap_orders
    if orders is None:
        orders = _get_opening_gap_orders(
            previous_close,
            candle,
            exchange,
            symbol,
            active_orders=active_orders,
        )
    if not orders:
        return False

    open_price = candle[1]
    opening_candle = candle.copy()
    opening_candle[2:5] = open_price
    opening_candle[5] = 0
    _update_all_routes_a_partial_candle(exchange, symbol, opening_candle)

    position = store.positions.get_position(exchange, symbol)
    if position:
        position.current_price = open_price

    # Both simulators timestamp fills at the end of the one-minute candle that
    # exposes the opening price.
    store.app.time = candle[0] + 60_000

    executed = False
    for order in orders:
        # Another fill at this open may close the position and cancel its siblings.
        if not order.is_active:
            continue

        # Order.price is the execution price used by accounting. Keep the
        # submitted trigger or limit available for diagnostics.
        order.vars = dict(order.vars or {})
        order.vars['submitted_price'] = order.price
        order.price = open_price
        order_service.execute_order(order)
        executed = True

    return executed


def _get_opening_gap_and_executing_orders(
        active_orders: List[Order],
        candle: np.ndarray,
        previous_close: Optional[float],
) -> Tuple[List[Order], List[Order]]:
    """Classify active orders for the opening gap and current candle in one pass."""
    if not active_orders:
        return [], []

    open_price = candle[1]
    high = candle[3]
    low = candle[4]
    upward_gap = previous_close is not None and open_price > previous_close
    downward_gap = previous_close is not None and open_price < previous_close
    opening_gap_orders = []
    executing_orders = []

    for order in active_orders:
        if not order.is_active:
            continue
        order_price = order.price
        if order_price is None:
            continue
        if low <= order_price <= high:
            executing_orders.append(order)
        if (
            upward_gap
            and previous_close <= order_price <= open_price
            and (
                (order.type == order_types.LIMIT and order.side == sides.SELL)
                or (order.type == order_types.STOP and order.side == sides.BUY)
            )
        ):
            opening_gap_orders.append(order)
        elif (
            downward_gap
            and open_price <= order_price <= previous_close
            and (
                (order.type == order_types.LIMIT and order.side == sides.BUY)
                or (order.type == order_types.STOP and order.side == sides.SELL)
            )
        ):
            opening_gap_orders.append(order)

    if len(opening_gap_orders) > 1:
        opening_gap_orders.sort(
            key=lambda order: order.price,
            reverse=open_price < previous_close,
        )
    return opening_gap_orders, executing_orders


def _simulate_price_change_effect(
        real_candle: np.ndarray,
        exchange: str,
        symbol: str,
        previous_close: Optional[float] = None,
) -> None:
    active_orders = store.orders.get_active_orders(exchange, symbol)
    opening_gap_orders, executing_orders = _get_opening_gap_and_executing_orders(
        active_orders,
        real_candle,
        previous_close,
    )
    any_order_executed = False
    if opening_gap_orders:
        any_order_executed = _execute_opening_gap_orders(
            previous_close,
            real_candle,
            exchange,
            symbol,
            opening_gap_orders=opening_gap_orders,
        )
    if any_order_executed:
        # Fill callbacks can cancel sibling orders or submit new protective orders.
        active_orders = store.orders.get_active_orders(exchange, symbol)
        executing_orders = _get_executing_orders(
            exchange,
            symbol,
            real_candle,
            active_orders=active_orders,
        )

    # the vast majority of candles have no order waiting to be executed inside
    # them, so only pay for the candle copy + execution loop when needed.
    if executing_orders:
        current_temp_candle = real_candle.copy()
        if len(executing_orders) > 1:
            # extend the candle shape from (6,) to (1,6)
            executing_orders = _sort_execution_orders(executing_orders, current_temp_candle[None, :])

        while True:
            executed_order = False

            for index, order in enumerate(executing_orders):
                if not order.is_active:
                    continue

                if candle_service.candle_includes_price(current_temp_candle, order.price):
                    storable_temp_candle, current_temp_candle = candle_service.split_candle(current_temp_candle, order.price)
                    _update_all_routes_a_partial_candle(exchange, symbol, storable_temp_candle)

                    p = store.positions.get_position(exchange, symbol)
                    p.current_price = storable_temp_candle[2]

                    executed_order = True
                    any_order_executed = True

                    order_service.execute_order(order)
                    executing_orders = _get_executing_orders(exchange, symbol, current_temp_candle)
                    if len(executing_orders) > 1:
                        # extend the candle shape from (6,) to (1,6)
                        executing_orders = _sort_execution_orders(executing_orders, current_temp_candle[None, :])

                    # break from the for loop, we'll try again inside the while
                    # loop with the new current_temp_candle
                    break

            if not executed_order:
                break

    if any_order_executed:
        # partial candles were stored during order execution; restore the
        # real_candle in the store so we can move on. When nothing executed,
        # the caller (_step_simulator) already added this exact candle right
        # before calling us, so there is nothing to restore.
        candle_service.add_candle(
            real_candle, exchange, symbol, '1m',
            with_execution=False,
            with_generation=False
        )

    p = store.positions.get_position(exchange, symbol)
    if p:
        p.current_price = real_candle[2]

    _check_for_liquidations(
        real_candle,
        exchange,
        symbol,
        position=p,
        previous_close=previous_close,
    )


def _check_for_liquidations(
        candle: np.ndarray,
        exchange: str,
        symbol: str,
        position: Position = None,
        previous_close: Optional[float] = None,
) -> None:
    # accept an already-fetched position to avoid a second lookup on the hot path
    p: Position = position if position is not None else store.positions.get_position(exchange, symbol)

    if not p:
        return

    # for now, we only support the isolated mode:
    if p.mode != 'isolated':
        return

    liquidation_reached = candle_service.candle_includes_price(candle, p.liquidation_price)
    if previous_close is not None:
        open_price = candle[1]
        liquidation_reached = liquidation_reached or (
            min(previous_close, open_price)
            <= p.liquidation_price
            <= max(previous_close, open_price)
        )

    if liquidation_reached:
        closing_order_side = jh.closing_side(p.type)

        # create the market order that is used as the liquidation order
        order = Order({
            'id': jh.generate_unique_id(),
            'symbol': symbol,
            'exchange': exchange,
            'side': closing_order_side,
            'type': order_types.MARKET,
            'reduce_only': True,
            'qty': jh.prepare_qty(p.qty, closing_order_side),
            'price': p.bankruptcy_price
        })

        store.orders.add_order(order)

        store.app.total_liquidations += 1

        logger.info(f'{p.symbol} liquidated at {p.liquidation_price}')

        order_service.execute_order(order)


def _generate_outputs(
        candles: dict,
        generate_csv: bool = False,
        generate_json: bool = False,
        generate_equity_curve: bool = False,
        benchmark: bool = False,
        generate_hyperparameters: bool = False,
        generate_logs: bool = False,
):
    result = {}
    if generate_hyperparameters:
        result["hyperparameters"] = stats.hyperparameters(router.routes)
    result["metrics"] = report.portfolio_metrics()
    result["trades"] = report.trades()
    # generate logs in json and csv format
    logs_path = store_logs(generate_json, generate_csv)
    if generate_json:
        result["json"] = logs_path["json"]
    if generate_csv:
        result["csv"] = logs_path["csv"]
    if generate_equity_curve:
        result["equity_curve"] = charts.equity_curve(benchmark)
    if generate_logs:
        result["logs"] = f"storage/logs/backtest-mode/{jh.get_session_id()}.txt"
    return result


def _skip_simulator(
        candles: dict,
        run_silently: bool,
        hyperparameters: dict = None,
        generate_csv: bool = False,
        generate_json: bool = False,
        generate_equity_curve: bool = False,
        benchmark: bool = False,
        generate_hyperparameters: bool = False,
        generate_logs: bool = False,
        with_candles_pipeline: bool = True,
        candles_pipeline_class = None,
        candles_pipeline_kwargs: dict = None,
) -> dict:
    if _uses_observed_timestamp_replay(candles):
        # The skip entry point shares the timestamp event core so sparse and
        # unequal streams retain step mode's atomic visibility and order rules.
        return _timestamp_simulator(
            candles,
            run_silently,
            fast_mode=True,
            hyperparameters=hyperparameters,
            generate_csv=generate_csv,
            generate_json=generate_json,
            generate_equity_curve=generate_equity_curve,
            benchmark=benchmark,
            generate_hyperparameters=generate_hyperparameters,
            generate_logs=generate_logs,
            with_candles_pipeline=with_candles_pipeline,
            candles_pipeline_class=candles_pipeline_class,
            candles_pipeline_kwargs=candles_pipeline_kwargs,
        )

    # In case generating logs is specifically demanded, the debug mode must be enabled.
    if generate_logs:
        config["app"]["debug_mode"] = True

    begin_time_track = time.time()

    length = _simulation_minutes_length(candles)
    _prepare_times_before_simulation(candles)
    candles_pipelines = _prepare_routes(hyperparameters, with_candles_pipeline, candles_pipeline_class, candles_pipeline_kwargs)

    # add initial balance
    save_daily_portfolio_balance(is_initial=True)
    # Preserve Jesse's historical first sample after row 1,440, then keep a
    # fixed daily schedule so delayed sparse rows do not shift later samples.
    next_balance_sample_time = int(store.app.time) + 86_460_000

    candles_step = _calculate_minimum_candle_step()

    # Pipeline-free, ascending float64 candles can be copied into storage once.
    # Order-free batches then advance the visible index without copying rows.
    prefilled = {}
    for j in candles:
        candles_arr = candles[j]['candles']
        if (
            candles_pipelines[j] is None
            and candles_arr.dtype == np.float64
            and candles_arr.flags.writeable
            and len(candles_arr) == length
            and not (candles_arr[:, 0] == 0).any()
            and (length < 2 or (np.diff(candles_arr[:, 0]) > 0).all())
        ):
            storage = store.candles.get_storage(candles[j]['exchange'], candles[j]['symbol'], '1m')
            base = storage.index + 1
            # warmup continuity: the series must strictly follow whatever
            # warmup candles already sit in storage
            if base == 0 or candles_arr[0, 0] > storage.array[base - 1, 0]:
                needed = base + length
                if needed > len(storage.array):
                    # Allocate enough room for the complete simulation range.
                    new_array = np.zeros((needed,) + storage.array.shape[1:], dtype=storage.array.dtype)
                    new_array[:base] = storage.array[:base]
                    storage.array = new_array
                storage.array[base:base + length] = candles_arr
                prefilled[j] = storage

    # hoist the per-step loop invariants out of the hot loop
    pairs_info = [
        (
            candles[j]['candles'],
            candles_pipelines[j],
            candles[j]['exchange'],
            candles[j]['symbol'],
            prefilled.get(j),
        )
        for j in candles
    ]
    htf_info = [
        (timeframe, TIMEFRAME_TO_ONE_MINUTES[timeframe])
        for timeframe in config['app']['considering_timeframes']
        if timeframe != '1m'
    ]

    progressbar = Progressbar(length, step=candles_step)
    last_update_time = None
    for i in range(0, length, candles_step):
        # update time moved to _simulate_price_change_effect__multiple_candles
        # store.app.time = first_candles_set[i][0] + (60_000 * candles_step)
        _simulate_new_candles(candles, candles_pipelines, i, candles_step, pairs_info, htf_info)

        last_update_time = _update_progress_bar(progressbar, run_silently, i + candles_step - 1, candles_step,
                                                last_update_time=last_update_time)

        _execute_routes(i, candles_step)

        # now check to see if there's any MARKET orders waiting to be executed
        order_service.execute_simulated_market_orders()

        # Timestamp-based sampling keeps sparse market closures as real gaps
        # instead of treating 1,440 available rows as one calendar day.
        if int(store.app.time) >= next_balance_sample_time:
            save_daily_portfolio_balance()
            while next_balance_sample_time <= int(store.app.time):
                next_balance_sample_time += 86_400_000

    _finish_progress_bar(progressbar, run_silently)

    execution_duration = 0
    if not run_silently:
        # print executed time for the backtest session
        finish_time_track = time.time()
        execution_duration = round(finish_time_track - begin_time_track, 2)

    for r in router.routes:
        r.strategy._terminate()
        order_service.execute_simulated_market_orders()

    # now that backtest simulation is finished, add finishing balance
    save_daily_portfolio_balance()

    # set the ending time for the backtest session
    store.app.ending_time = store.app.time + 60_000

    result = _generate_outputs(
        candles,
        generate_csv=generate_csv,
        generate_json=generate_json,
        generate_equity_curve=generate_equity_curve,
        benchmark=benchmark,
        generate_hyperparameters=generate_hyperparameters,
        generate_logs=generate_logs,
    )
    result['execution_duration'] = execution_duration
    return result


def _calculate_minimum_candle_step():
    """
    Calculates the minimum step for update candles that will allow simple updates on the simulator.
    """
    # config["app"]["considering_timeframes"] use '1m' also even if not required by the user so take only what the user
    # is requested.
    consider_time_frames = [
        TIMEFRAME_TO_ONE_MINUTES[route["timeframe"]]
        for route in router.all_formatted_routes
    ]
    return np.gcd.reduce(consider_time_frames)

timeframe_to_one_minutes = {
    timeframes.MINUTE_1: 1,
    timeframes.MINUTE_3: 3,
    timeframes.MINUTE_5: 5,
    timeframes.MINUTE_15: 15,
    timeframes.MINUTE_30: 30,
    timeframes.MINUTE_45: 45,
    timeframes.HOUR_1: 60,
    timeframes.HOUR_2: 60 * 2,
    timeframes.HOUR_3: 60 * 3,
    timeframes.HOUR_4: 60 * 4,
    timeframes.HOUR_6: 60 * 6,
    timeframes.HOUR_8: 60 * 8,
    timeframes.HOUR_12: 60 * 12,
    timeframes.DAY_1: 60 * 24,
    timeframes.DAY_3: 60 * 24 * 3,
    timeframes.WEEK_1: 60 * 24 * 7,
    timeframes.MONTH_1: 60 * 24 * 30,
}
def _simulate_new_candles(
        candles: dict,
        candles_pipelines: Dict[str, BaseCandlesPipeline],
        candle_index: int,
        candles_step: int,
        pairs_info: list = None,
        htf_info: list = None,
) -> None:
    i = candle_index
    # loop invariants (precomputed once by _skip_simulator; rebuilt here only
    # if this function is called standalone)
    if pairs_info is None:
        pairs_info = [
            (candles[j]['candles'], candles_pipelines[j], candles[j]['exchange'], candles[j]['symbol'], None)
            for j in candles
        ]
    if htf_info is None:
        htf_info = [
            (timeframe, TIMEFRAME_TO_ONE_MINUTES[timeframe])
            for timeframe in config['app']['considering_timeframes']
            if timeframe != '1m'
        ]

    i_step = i + candles_step
    generate_candle_from_one_minutes = candle_service.generate_candle_from_one_minutes
    add_candle = candle_service.add_candle

    # add candles
    for candles_arr, candles_pipeline, exchange, symbol, storage_1m in pairs_info:
        if storage_1m is not None:
            # These rows are already present in the 1m storage buffer.
            short_candles = candles_arr[i:i_step]
        else:
            short_candles = get_candles_from_pipeline(candles_pipeline, candles_arr, i, candles_step)
            candles_arr[i:i_step] = short_candles
        previous_close = candles_arr[i - 1, 2] if i != 0 else None
        real_candle = _simulate_price_change_effect_multiple_candles(
            short_candles,
            exchange,
            symbol,
            storage_1m,
            previous_close=previous_close,
        )

        # generate and add candles for bigger timeframes
        for timeframe, count in htf_info:
            if i_step % count == 0:
                if count == candles_step and (storage_1m is not None or candles_pipeline is None):
                    # The batch aggregate already represents this complete
                    # higher-timeframe candle, provided the rows came directly
                    # from the canonical candle array.
                    generated_candle = real_candle
                else:
                    generated_candle = generate_candle_from_one_minutes(
                        timeframe,
                        candles_arr[i_step - count: i_step],
                    )

                add_candle(
                    generated_candle,
                    exchange,
                    symbol,
                    timeframe,
                    with_execution=False,
                    with_generation=False,
                )


def _simulate_price_change_effect_multiple_candles(
        short_timeframes_candles: np.ndarray, exchange: str, symbol: str,
        prefilled_storage_1m=None,
        previous_close: Optional[float] = None,
) -> np.ndarray:
    if len(short_timeframes_candles) <= 4320 and short_timeframes_candles.dtype == np.float64:
        # bit-exact Rust kernel for the common case (see generate_candle_from_one_minutes)
        real_candle = candle_from_one_minutes_rust(short_timeframes_candles)
    else:
        real_candle = np.array(
            [
                short_timeframes_candles[0][0],
                short_timeframes_candles[0][1],
                short_timeframes_candles[-1][2],
                short_timeframes_candles[:, 3].max(),
                short_timeframes_candles[:, 4].min(),
                short_timeframes_candles[:, 5].sum(),
            ]
        )
    active_orders = store.orders.get_active_orders(exchange, symbol)
    boundary_gap_orders, executing_orders = _get_opening_gap_and_executing_orders(
        active_orders,
        real_candle,
        previous_close,
    )
    # Internal gaps are bounded by this aggregate candle's high and low, so an
    # order inside one already appears in executing_orders. Only the transition
    # from the previous batch needs a separate boundary-gap result.
    had_executing_orders = bool(executing_orders) or bool(boundary_gap_orders)
    if had_executing_orders:
        if len(executing_orders) > 1:
            executing_orders = _sort_execution_orders(executing_orders, short_timeframes_candles)

        for i in range(len(short_timeframes_candles)):
            current_temp_candle = short_timeframes_candles[i].copy()
            candle_previous_close = (
                short_timeframes_candles[i - 1, 2]
                if i > 0
                else previous_close
            )
            opening_gap_executed = _execute_opening_gap_orders(
                candle_previous_close,
                current_temp_candle,
                exchange,
                symbol,
                active_orders=active_orders,
            )
            if opening_gap_executed:
                # Fill callbacks can change the active set before intrabar execution.
                active_orders = store.orders.get_active_orders(exchange, symbol)
                executing_orders = _get_executing_orders(
                    exchange,
                    symbol,
                    real_candle,
                    active_orders=active_orders,
                )
                if len(executing_orders) > 1:
                    executing_orders = _sort_execution_orders(
                        executing_orders,
                        short_timeframes_candles[i:],
                    )
            is_executed_order = False

            while True:
                if len(executing_orders) == 0:
                    is_executed_order = False
                else:
                    for index, order in enumerate(executing_orders):
                        if index == len(executing_orders) - 1 and not order.is_active:
                            is_executed_order = False
                        if not order.is_active:
                            continue

                        if candle_service.candle_includes_price(current_temp_candle, order.price):
                            storable_temp_candle, current_temp_candle = candle_service.split_candle(
                                current_temp_candle, order.price
                            )
                            _update_all_routes_a_partial_candle(
                                exchange,
                                symbol,
                                storable_temp_candle,
                            )
                            p = store.positions.get_position(exchange, symbol)
                            p.current_price = storable_temp_candle[2]

                            is_executed_order = True

                            store.app.time = storable_temp_candle[0] + 60_000
                            order_service.execute_order(order)
                            active_orders = store.orders.get_active_orders(exchange, symbol)
                            executing_orders = _get_executing_orders(
                                exchange,
                                symbol,
                                real_candle,
                                active_orders=active_orders,
                            )

                            # break from the for loop, we'll try again inside the while
                            # loop with the new current_temp_candle
                            break
                        else:
                            is_executed_order = False

                if not is_executed_order:
                    # add/update the real_candle to the store so we can move on
                    candle_service.add_candle(
                        short_timeframes_candles[i].copy(),
                        exchange,
                        symbol,
                        "1m",
                        with_execution=False,
                        with_generation=False,
                    )
                    p = store.positions.get_position(exchange, symbol)
                    if p:
                        p.current_price = current_temp_candle[2]
                    break

    if prefilled_storage_1m is not None and not had_executing_orders:
        # The batch is already stored and no partial execution candles need
        # replacing, so only the visible storage index must advance.
        prefilled_storage_1m.index += len(short_timeframes_candles)
    else:
        candle_service.add_multiple_1m_candles(
            short_timeframes_candles,
            exchange,
            symbol,
        )
    store.app.time = real_candle[0] + (60_000 * len(short_timeframes_candles))
    _check_for_liquidations(
        real_candle,
        exchange,
        symbol,
        previous_close=previous_close,
    )

    p = store.positions.get_position(exchange, symbol)
    if p:
        p.current_price = short_timeframes_candles[-1, 2]

    return real_candle


def _update_all_routes_a_partial_candle(
        exchange: str,
        symbol: str,
        storable_temp_candle: np.ndarray,
) -> None:
    """
    This function get called when an order is getting executed you need to update the other timeframe how their last
    candles looks like
    """
    candle_service.add_candle(
        storable_temp_candle,
        exchange,
        symbol,
        "1m",
        with_execution=False,
        with_generation=False,
    )

    for route in router.all_formatted_routes:
        timeframe = route['timeframe']
        if route['exchange'] != exchange or route['symbol'] != symbol:
            continue
        if timeframe == '1m':
            continue
        tf_minutes = TIMEFRAME_TO_ONE_MINUTES[timeframe]
        number_of_needed_candles = int(storable_temp_candle[0] % (tf_minutes * 60_000) // 60000) + 1
        candles_1m = candle_service.get_candles(exchange, symbol, '1m')[-number_of_needed_candles:]
        generated_candle = candle_service.generate_candle_from_one_minutes(
            timeframe,
            candles_1m,
            accept_forming_candles=True
        )
        candle_service.add_candle(
            generated_candle,
            exchange,
            symbol,
            timeframe,
            with_execution=False,
            with_generation=False,
        )


def _execute_routes(candle_index: int, candles_step: int) -> None:
    # now that all new generated candles are ready, execute
    for r in router.routes:
        count = TIMEFRAME_TO_ONE_MINUTES[r.timeframe]
        # 1m timeframe
        if r.timeframe == timeframes.MINUTE_1:
            r.strategy._execute()
        elif (candle_index + candles_step) % count == 0:
            # print candle
            if jh.is_debuggable("trading_candles"):
                candle_service.print_candle(
                    candle_service.get_current_candle(
                        r.exchange, r.symbol, r.timeframe
                    ),
                    False,
                    r.symbol,
                )
            r.strategy._execute()

        order_service.update_active_orders(r.exchange, r.symbol)


def _get_executing_orders(
        exchange: str,
        symbol: str,
        real_candle: np.ndarray,
        active_orders: Optional[List[Order]] = None,
) -> List[Order]:
    if active_orders is None:
        active_orders = store.orders.get_active_orders(exchange, symbol)
    if not active_orders:
        return []
    # inlined candle_includes_price() with the candle's high/low hoisted out of the loop
    high = real_candle[3]
    low = real_candle[4]
    return [
        order
        for order in active_orders
        if order.is_active and low <= order.price <= high
    ]


def _sort_execution_orders(orders: List[Order], short_candles: np.ndarray):
    remaining_orders = set(orders)
    sorted_orders = []
    
    for candle in short_candles:
        open_price, close_price, low, high = candle[1], candle[2], candle[4], candle[3]

        # Did not use candle_includes_price() for performance, keeping it vectorization-friendly
        included_orders = [order for order in remaining_orders if low <= order.price <= high]

        if len(included_orders) == 1:
            sorted_orders.append(included_orders[0])
            remaining_orders.remove(included_orders[0])
        elif len(included_orders) > 1:
            # in case that the orders are above
            on_open, above_open, below_open = [], [], []
            for order in included_orders:
                if order.price == open_price:
                    on_open.append(order)
                if order.price > open_price:
                    above_open.append(order)
                else:
                    below_open.append(order)
            sorted_orders += on_open
            remaining_orders.difference_update(on_open)

            is_red = open_price > close_price
            if is_red:
                # heuristic that first the price goes up and then down, so this is the order execution sort
                above_open.sort(key=lambda o: o.price)
                below_open.sort(key=lambda o: o.price, reverse=True)
                sorted_orders += above_open + below_open
                remaining_orders.difference_update(above_open + below_open)
            else:
                below_open.sort(key=lambda o: o.price, reverse=True)
                above_open.sort(key=lambda o: o.price)
                sorted_orders += below_open + above_open
                remaining_orders.difference_update(below_open + above_open)

        if len(sorted_orders) == len(orders):
            break

    return sorted_orders
