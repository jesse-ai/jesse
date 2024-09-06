import time
import re
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd
import jesse.helpers as jh
import jesse.services.metrics as stats
import jesse.services.selectors as selectors
from jesse import exceptions
from jesse.config import config
from jesse.enums import timeframes, order_types
from jesse.models import Order, Position
from jesse.modes.utils import save_daily_portfolio_balance
from jesse.routes import router
from jesse.services import charts
from jesse.services import quantstats
from jesse.services import report
from jesse.services.candle import generate_candle_from_one_minutes, print_candle, candle_includes_price, split_candle, \
    get_candles, inject_warmup_candles_to_store
from jesse.services.file import store_logs
from jesse.services.validators import validate_routes
from jesse.store import store
from jesse.services import logger
from jesse.services.failure import register_custom_exception_handler
from jesse.services.redis import sync_publish, is_process_active
from timeloop import Timeloop
from datetime import timedelta
from jesse.services.progressbar import Progressbar


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
        tradingview: bool = False,
        full_reports: bool = False,
        csv: bool = False,
        json: bool = False,
        fast_mode: bool = False,
        benchmark: bool = False
) -> None:
    if not jh.is_unit_testing():
        # at every second, we check to see if it's time to execute stuff
        status_checker = Timeloop()

        @status_checker.job(interval=timedelta(seconds=1))
        def handle_time():
            if is_process_active(client_id) is False:
                raise exceptions.Termination

        status_checker.start()

    from jesse.config import config
    config['app']['trading_mode'] = 'backtest'

    # debug flag
    config['app']['debug_mode'] = debug_mode

    register_custom_exception_handler()

    _execute_backtest(
        client_id, debug_mode, user_config, exchange, routes, data_routes, start_date, finish_date, candles, chart,
        tradingview, full_reports, csv, json, fast_mode, benchmark
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
        tradingview: bool = False,
        full_reports: bool = False,
        csv: bool = False,
        json: bool = False,
        fast_mode: bool = False,
        benchmark: bool = False
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

    store.app.set_session_id(client_id)

    # validate routes
    validate_routes(router)

    # initiate candle store
    store.candles.init_storage(5000)

    # load historical candles
    if candles is None:
        warmup_candles, candles = load_candles(
            jh.date_to_timestamp(start_date),
            jh.date_to_timestamp(finish_date)
        )
        _handle_warmup_candles(warmup_candles)

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
        result = simulator(
            candles,
            run_silently=jh.should_execute_silently(),
            generate_tradingview=tradingview,
            generate_quantstats=full_reports,
            generate_csv=csv,
            generate_json=json,
            generate_equity_curve=True,
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
                chart, tradingview, full_reports, csv, json, fast_mode, benchmark
            )
        else:
            raise e

    if result and not jh.should_execute_silently():
        sync_publish('alert', {
            'message': f"Successfully executed backtest simulation in: {result['execution_duration']} seconds",
            'type': 'success'
        })
        sync_publish('hyperparameters', result['hyperparameters'])
        sync_publish('metrics', result['metrics'])
        sync_publish('equity_curve', result['equity_curve'], compression=True)
        if chart:
            sync_publish('candles_chart', _get_formatted_candles_for_frontend(), compression=True)
            sync_publish('orders_chart', _get_formatted_orders_for_frontend(), compression=True)
            sync_publish('add_line_to_candle_chart', _get_add_line_to_candle_chart(), compression=True)
            sync_publish('add_extra_line_chart', _get_add_extra_line_chart(), compression=True)
            sync_publish('add_horizontal_line_to_candle_chart', _get_add_horizontal_line_to_candle_chart(), compression=True)
            sync_publish('add_horizontal_line_to_extra_chart', _get_add_horizontal_line_to_extra_chart(), compression=True)

    # close database connection
    from jesse.services.db import database
    database.close_connection()


def _get_formatted_candles_for_frontend():
    arr = []
    for r in router.routes:
        candles_arr = store.candles.get_candles(r.exchange, r.symbol, r.timeframe)
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


def _generate_quantstats_report(candles_dict: dict) -> str:
    if store.completed_trades.count == 0:
        return None

    price_data = []
    timestamps = []
    # load close candles for Buy and hold and calculate pct_change
    for index, c in enumerate(config['app']['considering_candles']):
        exchange, symbol = c[0], c[1]
        if exchange in config['app']['trading_exchanges'] and symbol in config['app']['trading_symbols']:
            candles = candles_dict[jh.key(exchange, symbol)]['candles']

            # if timestamps is empty, fill it with the first candles timestamps because it's the same for all candles
            if timestamps == []:
                timestamps = candles[:, 0]
            price_data.append(candles[:, 1])

    price_data = np.transpose(price_data)
    price_df = pd.DataFrame(
        price_data, index=pd.to_datetime(timestamps, unit="ms"), dtype=float
    ).resample('D').mean()
    price_pct_change = price_df.pct_change(1).fillna(0)
    buy_and_hold_daily_returns_all_routes = price_pct_change.mean(1)
    study_name = _get_study_name()
    res = quantstats.quantstats_tearsheet(buy_and_hold_daily_returns_all_routes, study_name)
    return res


def _get_study_name() -> str:
    routes_count = len(router.routes)
    more = f"-and-{routes_count - 1}-more" if routes_count > 1 else ""
    if type(router.routes[0].strategy_name) is str:
        strategy_name = router.routes[0].strategy_name
    else:
        strategy_name = router.routes[0].strategy_name.__name__
    study_name = f"{strategy_name}-{router.routes[0].exchange}-{router.routes[0].symbol}-{router.routes[0].timeframe}{more}"
    return study_name


def load_candles(start_date: int, finish_date: int) -> Tuple[dict, dict]:
    warmup_num = jh.get_config('env.data.warmup_candles_num', 210)
    max_timeframe = jh.max_timeframe(config['app']['considering_timeframes'])

    # load and add required warm-up candles for backtest, and then Prepare trading candles
    trading_candles = {}
    warmup_candles = {}
    for c in config['app']['considering_candles']:
        exchange, symbol = c[0], c[1]
        warmup_candles_arr, trading_candle_arr = get_candles(
            exchange, symbol, max_timeframe, start_date, finish_date, warmup_num, caching=True, is_for_jesse=True
        )

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


def _handle_warmup_candles(warmup_candles: dict) -> None:
    for c in config['app']['considering_candles']:
        exchange, symbol = c[0], c[1]
        inject_warmup_candles_to_store(warmup_candles[jh.key(exchange, symbol)]['candles'], exchange, symbol)


def simulator(*args, fast_mode: bool = False, **kwargs) -> dict:
    if fast_mode:
        return _skip_simulator(*args, **kwargs)

    return _step_simulator(*args, **kwargs)


def _step_simulator(
        candles: dict,
        run_silently: bool,
        hyperparameters: dict = None,
        generate_tradingview: bool = False,
        generate_quantstats: bool = False,
        generate_csv: bool = False,
        generate_json: bool = False,
        generate_equity_curve: bool = False,
        benchmark: bool = False,
        generate_hyperparameters: bool = False,
        generate_logs: bool = False,
) -> dict:
    # In case generating logs is specifically demanded, the debug mode must be enabled.
    if generate_logs:
        config['app']['debug_mode'] = True

    begin_time_track = time.time()

    key = f"{config['app']['considering_candles'][0][0]}-{config['app']['considering_candles'][0][1]}"
    first_candles_set = candles[key]['candles']

    length = _simulation_minutes_length(candles)
    _prepare_times_before_simulation(candles)
    _prepare_routes(hyperparameters)

    # add initial balance
    save_daily_portfolio_balance(is_initial=True)

    progressbar = Progressbar(length, step=420)
    last_update_time = None
    for i in range(length):
        # update time
        store.app.time = first_candles_set[i][0] + 60_000

        # add candles
        for j in candles:
            short_candle = candles[j]['candles'][i]
            if i != 0:
                previous_short_candle = candles[j]['candles'][i - 1]
                short_candle = _get_fixed_jumped_candle(previous_short_candle, short_candle)
            exchange = candles[j]['exchange']
            symbol = candles[j]['symbol']

            store.candles.add_candle(short_candle, exchange, symbol, '1m', with_execution=False,
                                     with_generation=False)

            # print short candle
            if jh.is_debuggable('shorter_period_candles'):
                print_candle(short_candle, True, symbol)

            _simulate_price_change_effect(short_candle, exchange, symbol)

            # generate and add candles for bigger timeframes
            for timeframe in config['app']['considering_timeframes']:
                # for 1m, no work is needed
                if timeframe == '1m':
                    continue

                count = jh.timeframe_to_one_minutes(timeframe)
                # until = count - ((i + 1) % count)

                if (i + 1) % count == 0:
                    generated_candle = generate_candle_from_one_minutes(
                        timeframe,
                        candles[j]['candles'][(i - (count - 1)):(i + 1)]
                    )

                    store.candles.add_candle(generated_candle, exchange, symbol, timeframe, with_execution=False,
                                             with_generation=False)

        last_update_time = _update_progress_bar(progressbar, run_silently, i, candle_step=420,
                                                last_update_time=last_update_time)

        # now that all new generated candles are ready, execute
        for r in router.routes:
            count = jh.timeframe_to_one_minutes(r.timeframe)
            # 1m timeframe
            if r.timeframe == timeframes.MINUTE_1:
                r.strategy._execute()
            elif (i + 1) % count == 0:
                # print candle
                if jh.is_debuggable('trading_candles'):
                    print_candle(store.candles.get_current_candle(r.exchange, r.symbol, r.timeframe), False,
                                 r.symbol)
                r.strategy._execute()

            store.orders.update_active_orders(r.exchange, r.symbol)

        # now check to see if there's any MARKET orders waiting to be executed
        _execute_market_orders()

        if i != 0 and i % 1440 == 0:
            save_daily_portfolio_balance()

    _finish_progress_bar(progressbar, run_silently)

    execution_duration = 0
    if not run_silently:
        # print executed time for the backtest session
        finish_time_track = time.time()
        execution_duration = round(finish_time_track - begin_time_track, 2)

    for r in router.routes:
        r.strategy._terminate()
        _execute_market_orders()

    # now that backtest simulation is finished, add finishing balance
    save_daily_portfolio_balance()

    # set the ending time for the backtest session
    store.app.ending_time = store.app.time + 60_000

    result = _generate_outputs(
        candles,
        generate_tradingview=generate_tradingview,
        generate_quantstats=generate_quantstats,
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


def _prepare_routes(hyperparameters: dict = None) -> None:
    # initiate strategies
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
                "Looks like the structure of your strategy directory is incorrect. Make sure to include the strategy INSIDE the __init__.py file. Another reason for this error might be that your strategy is missing the mandatory methods such as should_long(), go_long(), and should_cancel_entry(). "
                "\nIf you need working examples, check out: https://github.com/jesse-ai/example-strategies"
            )
        except:
            raise

        r.strategy.name = r.strategy_name
        r.strategy.exchange = r.exchange
        r.strategy.symbol = r.symbol
        r.strategy.timeframe = r.timeframe

        # read the dna from strategy's dna() and use it for injecting inject hyperparameters
        # first convert DNS string into hyperparameters
        if len(r.strategy.dna()) > 0 and hyperparameters is None:
            hyperparameters = jh.dna_to_hp(
                r.strategy.hyperparameters(), r.strategy.dna()
            )

        # inject hyperparameters sent within the optimize mode
        if hyperparameters is not None:
            r.strategy.hp = hyperparameters

        # init few objects that couldn't be initiated in Strategy __init__
        # it also injects hyperparameters into self.hp in case the route does not uses any DNAs
        r.strategy._init_objects()

        selectors.get_position(r.exchange, r.symbol).strategy = r.strategy


def _update_progress_bar(
        progressbar: Progressbar, run_silently: bool, candle_index: int, candle_step: int, last_update_time: float
) -> float:
    throttle_interval = 0.5
    current_time = time.time()
    if not run_silently and candle_index % candle_step == 0:
        progressbar.update()

        if last_update_time is None or (current_time - last_update_time) >= throttle_interval:
            sync_publish(
                "progressbar",
                {
                    "current": progressbar.current,
                    "estimated_remaining_seconds": progressbar.estimated_remaining_seconds,
                },
            )
            # Update the last update time
            last_update_time = current_time

    # Return the last update time for future reference
    return last_update_time


def _finish_progress_bar(progressbar: Progressbar, run_silently: bool):
    if run_silently:
        return

    progressbar.finish()
    sync_publish(
        "progressbar",
        {
            "current": 100,
            "estimated_remaining_seconds": 0,
        },
    )


def _get_fixed_jumped_candle(
        previous_candle: np.ndarray, candle: np.ndarray
) -> np.ndarray:
    """
    A little workaround for the times that the price has jumped and the opening
    price of the current candle is not equal to the previous candle's close!

    :param previous_candle: np.ndarray
    :param candle: np.ndarray
    """
    if previous_candle[2] < candle[1]:
        candle[1] = previous_candle[2]
        candle[4] = min(previous_candle[2], candle[4])
    elif previous_candle[2] > candle[1]:
        candle[1] = previous_candle[2]
        candle[3] = max(previous_candle[2], candle[3])

    return candle


def _simulate_price_change_effect(real_candle: np.ndarray, exchange: str, symbol: str) -> None:
    current_temp_candle = real_candle.copy()
    executed_order = False

    executing_orders = _get_executing_orders(exchange, symbol, real_candle)
    if len(executing_orders) > 1:
        # extend the candle shape from (6,) to (1,6)
        executing_orders = _sort_execution_orders(executing_orders, current_temp_candle[None, :])

    while True:
        if len(executing_orders) == 0:
            executed_order = False
        else:
            for index, order in enumerate(executing_orders):
                if index == len(executing_orders) - 1 and not order.is_active:
                    executed_order = False

                if not order.is_active:
                    continue

                if candle_includes_price(current_temp_candle, order.price):
                    storable_temp_candle, current_temp_candle = split_candle(current_temp_candle, order.price)
                    _update_all_routes_a_partial_candle(exchange, symbol, storable_temp_candle)

                    p = selectors.get_position(exchange, symbol)
                    p.current_price = storable_temp_candle[2]

                    executed_order = True

                    order.execute()
                    executing_orders = _get_executing_orders(exchange, symbol, real_candle)

                    # break from the for loop, we'll try again inside the while
                    # loop with the new current_temp_candle
                    break
                else:
                    executed_order = False

        if not executed_order:
            # add/update the real_candle to the store so we can move on
            store.candles.add_candle(
                real_candle, exchange, symbol, '1m',
                with_execution=False,
                with_generation=False
            )
            p = selectors.get_position(exchange, symbol)
            if p:
                p.current_price = real_candle[2]
            break

    _check_for_liquidations(real_candle, exchange, symbol)


def _check_for_liquidations(candle: np.ndarray, exchange: str, symbol: str) -> None:
    p: Position = selectors.get_position(exchange, symbol)

    if not p:
        return

    # for now, we only support the isolated mode:
    if p.mode != 'isolated':
        return

    if candle_includes_price(candle, p.liquidation_price):
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

        order.execute()


def _generate_outputs(
        candles: dict,
        generate_tradingview: bool = False,
        generate_quantstats: bool = False,
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
    # generate logs in json, csv and tradingview's pine-editor format
    logs_path = store_logs(generate_json, generate_tradingview, generate_csv)
    if generate_json:
        result["json"] = logs_path["json"]
    if generate_tradingview:
        result["tradingview"] = logs_path["tradingview"]
    if generate_csv:
        result["csv"] = logs_path["csv"]
    if generate_equity_curve:
        result["equity_curve"] = charts.equity_curve(benchmark)
    if generate_quantstats:
        result["quantstats"] = _generate_quantstats_report(candles)
    if generate_logs:
        result["logs"] = f"storage/logs/backtest-mode/{jh.get_session_id()}.txt"
    return result


def _skip_simulator(
        candles: dict,
        run_silently: bool,
        hyperparameters: dict = None,
        generate_tradingview: bool = False,
        generate_quantstats: bool = False,
        generate_csv: bool = False,
        generate_json: bool = False,
        generate_equity_curve: bool = False,
        benchmark: bool = False,
        generate_hyperparameters: bool = False,
        generate_logs: bool = False,
) -> dict:
    # In case generating logs is specifically demanded, the debug mode must be enabled.
    if generate_logs:
        config["app"]["debug_mode"] = True

    begin_time_track = time.time()

    length = _simulation_minutes_length(candles)
    _prepare_times_before_simulation(candles)
    _prepare_routes(hyperparameters)

    # add initial balance
    save_daily_portfolio_balance(is_initial=True)

    candles_step = _calculate_minimum_candle_step()
    progressbar = Progressbar(length, step=candles_step)
    last_update_time = None
    for i in range(0, length, candles_step):
        # update time moved to _simulate_price_change_effect__multiple_candles
        # store.app.time = first_candles_set[i][0] + (60_000 * candles_step)
        _simulate_new_candles(candles, i, candles_step)

        last_update_time = _update_progress_bar(progressbar, run_silently, i, candles_step,
                                                last_update_time=last_update_time)

        _execute_routes(i, candles_step)

        # now check to see if there's any MARKET orders waiting to be executed
        _execute_market_orders()

        if i != 0 and i % 1440 == 0:
            save_daily_portfolio_balance()

    _finish_progress_bar(progressbar, run_silently)

    execution_duration = 0
    if not run_silently:
        # print executed time for the backtest session
        finish_time_track = time.time()
        execution_duration = round(finish_time_track - begin_time_track, 2)

    for r in router.routes:
        r.strategy._terminate()
        _execute_market_orders()

    # now that backtest simulation is finished, add finishing balance
    save_daily_portfolio_balance()

    # set the ending time for the backtest session
    store.app.ending_time = store.app.time + 60_000

    result = _generate_outputs(
        candles,
        generate_tradingview=generate_tradingview,
        generate_quantstats=generate_quantstats,
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
        jh.timeframe_to_one_minutes(route["timeframe"])
        for route in router.all_formatted_routes
    ]
    return np.gcd.reduce(consider_time_frames)


def _simulate_new_candles(candles: dict, candle_index: int, candles_step: int) -> None:
    i = candle_index
    # add candles
    for j in candles:
        short_candles = candles[j]["candles"][i: i + candles_step]
        if i != 0:
            previous_short_candles = candles[j]["candles"][i - 1]
            # work the same, the fix needs to be done only on the gap of 1m edge candles.
            short_candles[0] = _get_fixed_jumped_candle(
                previous_short_candles, short_candles[0]
            )
        exchange = candles[j]["exchange"]
        symbol = candles[j]["symbol"]

        _simulate_price_change_effect_multiple_candles(
            short_candles, exchange, symbol
        )

        # generate and add candles for bigger timeframes
        for timeframe in config["app"]["considering_timeframes"]:
            # for 1m, no work is needed
            if timeframe == "1m":
                continue

            count = jh.timeframe_to_one_minutes(timeframe)

            if (i + candles_step) % count == 0:
                generated_candle = generate_candle_from_one_minutes(
                    timeframe,
                    candles[j]["candles"][
                    i - count + candles_step: i + candles_step],
                )

                store.candles.add_candle(
                    generated_candle,
                    exchange,
                    symbol,
                    timeframe,
                    with_execution=False,
                    with_generation=False,
                )


def _simulate_price_change_effect_multiple_candles(
        short_timeframes_candles: np.ndarray, exchange: str, symbol: str
) -> None:
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
    executing_orders = _get_executing_orders(exchange, symbol, real_candle)
    if len(executing_orders) > 0:
        if len(executing_orders) > 1:
            executing_orders = _sort_execution_orders(executing_orders, short_timeframes_candles)

        for i in range(len(short_timeframes_candles)):
            current_temp_candle = short_timeframes_candles[i].copy()
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

                        if candle_includes_price(current_temp_candle, order.price):
                            storable_temp_candle, current_temp_candle = split_candle(
                                current_temp_candle, order.price
                            )
                            _update_all_routes_a_partial_candle(
                                exchange,
                                symbol,
                                storable_temp_candle,
                            )
                            p = selectors.get_position(exchange, symbol)
                            p.current_price = storable_temp_candle[2]

                            is_executed_order = True

                            store.app.time = storable_temp_candle[0] + 60_000
                            order.execute()
                            executing_orders = _get_executing_orders(
                                exchange, symbol, real_candle
                            )

                            # break from the for loop, we'll try again inside the while
                            # loop with the new current_temp_candle
                            break
                        else:
                            is_executed_order = False

                if not is_executed_order:
                    # add/update the real_candle to the store so we can move on
                    store.candles.add_candle(
                        short_timeframes_candles[i].copy(),
                        exchange,
                        symbol,
                        "1m",
                        with_execution=False,
                        with_generation=False,
                    )
                    p = selectors.get_position(exchange, symbol)
                    if p:
                        p.current_price = current_temp_candle[2]
                    break

    store.candles.add_multiple_1m_candles(
        short_timeframes_candles,
        exchange,
        symbol,
    )
    store.app.time = real_candle[0] + (60_000 * len(short_timeframes_candles))
    _check_for_liquidations(real_candle, exchange, symbol)

    p = selectors.get_position(exchange, symbol)
    if p:
        p.current_price = short_timeframes_candles[-1, 2]


def _update_all_routes_a_partial_candle(
        exchange: str,
        symbol: str,
        storable_temp_candle: np.ndarray,
) -> None:
    """
    This function get called when an order is getting executed you need to update the other timeframe how their last
    candles looks like
    """
    store.candles.add_candle(
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
        tf_minutes = jh.timeframe_to_one_minutes(timeframe)
        number_of_needed_candles = int(storable_temp_candle[0] % (tf_minutes * 60_000) // 60000) + 1
        candles_1m = store.candles.get_candles(exchange, symbol, '1m')[-number_of_needed_candles:]
        generated_candle = generate_candle_from_one_minutes(
            timeframe,
            candles_1m,
            accept_forming_candles=True
        )
        store.candles.add_candle(
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
        count = jh.timeframe_to_one_minutes(r.timeframe)
        # 1m timeframe
        if r.timeframe == timeframes.MINUTE_1:
            r.strategy._execute()
        elif (candle_index + candles_step) % count == 0:
            # print candle
            if jh.is_debuggable("trading_candles"):
                print_candle(
                    store.candles.get_current_candle(
                        r.exchange, r.symbol, r.timeframe
                    ),
                    False,
                    r.symbol,
                )
            r.strategy._execute()

        store.orders.update_active_orders(r.exchange, r.symbol)


def _execute_market_orders():
    store.orders.execute_pending_market_orders()


def _get_executing_orders(exchange, symbol, real_candle):
    orders = store.orders.get_active_orders(exchange, symbol)
    return [
        order
        for order in orders
        if order.is_active and candle_includes_price(real_candle, order.price)
    ]


def _sort_execution_orders(orders: List[Order], short_candles: np.ndarray):
    sorted_orders = []
    for i in range(len(short_candles)):
        included_orders = [
            order
            for order in orders
            if candle_includes_price(short_candles[i], order.price)
        ]
        if len(included_orders) == 1:
            sorted_orders.append(included_orders[0])
        elif len(included_orders) > 1:
            # in case that the orders are above

            # note: check the first is enough because I can assume all the orders in the same direction of the price,
            # in case it doesn't than i cant really know how the price react in this 1 minute candle..
            if short_candles[i, 3] > included_orders[0].price > short_candles[i, 1]:
                sorted_orders += sorted(included_orders, key=lambda o: o.price)
            else:
                sorted_orders += sorted(included_orders, key=lambda o: o.price, reverse=True)
        if len(sorted_orders) == len(orders):
            break
    return sorted_orders
