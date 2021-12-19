import os
from multiprocessing import cpu_count
from typing import Dict, List
import arrow
import click
import jesse.helpers as jh
from jesse.modes.backtest_mode import load_candles
from jesse.services.validators import validate_routes
from jesse.store import store
from .Optimize import Optimizer
from jesse.services.failure import register_custom_exception_handler
from jesse.routes import router

os.environ['NUMEXPR_MAX_THREADS'] = str(cpu_count())


def run(
        debug_mode,
        user_config: dict,
        routes: List[Dict[str, str]],
        extra_routes: List[Dict[str, str]],
        start_date: str,
        finish_date: str,
        optimal_total: int,
        csv: bool,
        json: bool
) -> None:
    from jesse.config import config, set_config
    config['app']['trading_mode'] = 'optimize'

    # debug flag
    config['app']['debug_mode'] = debug_mode

    cpu_cores = int(user_config['cpu_cores'])

    # inject config
    set_config(user_config)

    # set routes
    router.initiate(routes, extra_routes)

    store.app.set_session_id()

    register_custom_exception_handler()

    # clear the screen
    if not jh.should_execute_silently():
        click.clear()

    # validate routes
    validate_routes(router)

    print('loading candles...')

    # load historical candles and divide them into training
    # and testing periods (15% for test, 85% for training)
    training_candles, testing_candles = _get_training_and_testing_candles(start_date, finish_date)

    # clear the screen
    click.clear()

    optimizer = Optimizer(
        training_candles, testing_candles, optimal_total, cpu_cores, csv, json, start_date, finish_date
    )

    # start the process
    optimizer.run()


def _get_training_and_testing_candles(start_date_str: str, finish_date_str: str) -> tuple:
    start_date = jh.arrow_to_timestamp(arrow.get(start_date_str, 'YYYY-MM-DD'))
    finish_date = jh.arrow_to_timestamp(arrow.get(finish_date_str, 'YYYY-MM-DD')) - 60000

    # Load candles (first try cache, then database)
    candles = load_candles(start_date_str, finish_date_str)

    # divide into training(85%) and testing(15%) sets
    training_candles = {}
    testing_candles = {}
    days_diff = jh.date_diff_in_days(jh.timestamp_to_arrow(start_date), jh.timestamp_to_arrow(finish_date))
    divider_index = int(days_diff * 0.85) * 1440
    for key in candles:
        training_candles[key] = {
            'exchange': candles[key]['exchange'],
            'symbol': candles[key]['symbol'],
            'candles': candles[key]['candles'][0:divider_index],
        }

        testing_candles[key] = {
            'exchange': candles[key]['exchange'],
            'symbol': candles[key]['symbol'],
            'candles': candles[key]['candles'][divider_index:],
        }

    return training_candles, testing_candles
