import math
import time
from datetime import timedelta
from typing import Dict, List, Any, Union

import arrow
import pydash
from timeloop import Timeloop

import jesse.helpers as jh
from jesse.exceptions import CandleNotFoundInExchange
from jesse.models import Candle
from jesse.modes.import_candles_mode.drivers import drivers, driver_names
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from jesse.config import config
from jesse.services.failure import register_custom_exception_handler
from jesse.services.redis import sync_publish, is_process_active
from jesse.store import store
from jesse import exceptions
from jesse.services.progressbar import Progressbar


def run(
        client_id: str,
        exchange: str,
        symbol: str,
        start_date_str: str,
        mode: str = 'candles',
        running_via_dashboard: bool = True,
        show_progressbar: bool = False,
):
    if running_via_dashboard:
        config['app']['trading_mode'] = mode
        register_custom_exception_handler()
        store.app.set_session_id(client_id)

    # open database connection
    from jesse.services.db import database
    database.open_connection()

    if running_via_dashboard:
        # at every second, we check to see if it's time to execute stuff
        status_checker = Timeloop()

        @status_checker.job(interval=timedelta(seconds=1))
        def handle_time():
            if is_process_active(client_id) is False:
                raise exceptions.Termination

        status_checker.start()

    try:
        start_timestamp = jh.arrow_to_timestamp(arrow.get(start_date_str, 'YYYY-MM-DD'))
    except:
        raise ValueError(
            f'start_date must be a string representing a date before today. ex: 2020-01-17. You entered: {start_date_str}')

    # more start_date validations
    today = arrow.utcnow().floor('day').int_timestamp * 1000
    if start_timestamp == today:
        raise ValueError("Today's date is not accepted. start_date must be a string a representing date BEFORE today.")
    elif start_timestamp > today:
        raise ValueError("Future's date is not accepted. start_date must be a string a representing date BEFORE today.")

    # We just call this to throw a exception in case of a symbol without dash
    jh.quote_asset(symbol)

    symbol = symbol.upper()

    until_date = arrow.utcnow().floor('day')
    start_date = arrow.get(start_timestamp / 1000)
    days_count = jh.date_diff_in_days(start_date, until_date)
    candles_count = days_count * 1440

    try:
        driver: CandleExchange = drivers[exchange]()
    except KeyError:
        raise ValueError(f'{exchange} is not a supported exchange. Supported exchanges are: {driver_names}')

    loop_length = int(candles_count / driver.count) + 1

    progressbar = Progressbar(loop_length, step=2)
    for i in range(candles_count):
        temp_start_timestamp = start_date.int_timestamp * 1000
        temp_end_timestamp = temp_start_timestamp + (driver.count - 1) * 60000

        # to make sure it won't try to import candles from the future! LOL
        if temp_start_timestamp > jh.now_to_timestamp():
            break

        # prevent duplicates calls to boost performance
        count = Candle.select().where(
            Candle.exchange == exchange,
            Candle.symbol == symbol,
            Candle.timeframe == '1m' or Candle.timeframe.is_null(),
            Candle.timestamp.between(temp_start_timestamp, temp_end_timestamp)
        ).count()
        already_exists = count == driver.count

        if not already_exists:
            # it's today's candles if temp_end_timestamp < now
            if temp_end_timestamp > jh.now_to_timestamp():
                temp_end_timestamp = arrow.utcnow().floor('minute').int_timestamp * 1000 - 60000

            # fetch from market
            candles = driver.fetch(symbol, temp_start_timestamp, timeframe='1m')

            # check if candles have been returned and check those returned start with the right timestamp.
            # Sometimes exchanges just return the earliest possible candles if the start date doesn't exist.
            time_diff = int((candles[0]['timestamp'] - temp_start_timestamp) / 1000) if len(candles) else 0
            if not len(candles) or time_diff < 0 or time_diff > 60*100:
                first_existing_timestamp = driver.get_starting_time(symbol)

                # if driver can't provide accurate get_starting_time()
                if first_existing_timestamp is None:
                    raise CandleNotFoundInExchange(
                        f'No candles exists in the market for this day: {jh.timestamp_to_time(temp_start_timestamp)[:10]} \n'
                        'Try another start_date'
                    )

                # handle when there's missing candles during the period
                if temp_start_timestamp > first_existing_timestamp:
                    # see if there are candles for the same date for the backup exchange,
                    # if so, get those, if not, download from that exchange.
                    if driver.backup_exchange is not None:
                        candles = _get_candles_from_backup_exchange(
                            exchange, driver.backup_exchange, symbol, temp_start_timestamp, temp_end_timestamp
                        )

                else:
                    temp_start_time = jh.timestamp_to_time(temp_start_timestamp)[:10]
                    temp_existing_time = jh.timestamp_to_time(first_existing_timestamp)[:10]
                    msg = f'No candle exists in the market for {temp_start_time}. So Jesse started importing since the first existing date which is {temp_existing_time}'
                    if running_via_dashboard:
                        sync_publish('alert', {
                            'message': msg,
                            'type': 'success'
                        })
                    else:
                        print(msg)
                    run(client_id, exchange, symbol, jh.timestamp_to_time(first_existing_timestamp)[:10], mode,
                        running_via_dashboard, show_progressbar)
                    return

            # fill absent candles (if there's any)
            candles = _fill_absent_candles(candles, temp_start_timestamp, temp_end_timestamp)

            # store in the database
            store_candles_list(candles)

        # add as much as driver's count to the temp_start_time
        start_date = start_date.shift(minutes=driver.count)

        if i % 2 == 0:
            progressbar.update()
        if running_via_dashboard:
            sync_publish('progressbar', {
                'current': progressbar.current,
                'estimated_remaining_seconds': progressbar.estimated_remaining_seconds
            })
        elif show_progressbar:
            jh.clear_output()
            print(
                f"Progress: {progressbar.current}% - {round(progressbar.estimated_remaining_seconds)} seconds remaining")

        # sleep so that the exchange won't get angry at us
        if not already_exists:
            time.sleep(driver.sleep_time)

    success_text = f'Successfully imported candles for {symbol} from {exchange} since {jh.timestamp_to_date(start_timestamp)} until today ({days_count} days). '

    # stop the status_checker time loop
    if running_via_dashboard:
        status_checker.stop()

        sync_publish('alert', {
            'message': success_text,
            'type': 'success'
        })

    # # TODO: shen should it close the database?
    # # if it is to skip, then it's being called from another process hence we should leave the database be
    # if not skip_confirmation:
    if not running_via_dashboard:
        # close database connection
        from jesse.services.db import database
        database.close_connection()
        return success_text


def _get_candles_from_backup_exchange(exchange: str, backup_driver: CandleExchange, symbol: str, start_timestamp: int,
                                      end_timestamp: int) -> List[Dict[str, Union[str, Any]]]:
    timeframe = '1m'
    total_candles = []
    # try fetching from database first
    backup_candles = Candle.select(
        Candle.timestamp, Candle.open, Candle.close, Candle.high, Candle.low,
        Candle.volume
    ).where(
        Candle.exchange == backup_driver.name,
        Candle.symbol == symbol,
        Candle.timeframe == timeframe,
        Candle.timestamp.between(start_timestamp, end_timestamp)
    ).order_by(Candle.timestamp.asc()).tuples()
    already_exists = len(backup_candles) == (end_timestamp - start_timestamp) / 60_000 + 1
    if already_exists:
        # loop through them and set new ID and exchange
        for c in backup_candles:
            total_candles.append({
                'id': jh.generate_unique_id(),
                'exchange': exchange,
                'symbol': symbol,
                'timeframe': timeframe,
                'timestamp': c[0],
                'open': c[1],
                'close': c[2],
                'high': c[3],
                'low': c[4],
                'volume': c[5]
            })

        return total_candles

    # try fetching from market now
    days_count = jh.date_diff_in_days(jh.timestamp_to_arrow(start_timestamp), jh.timestamp_to_arrow(end_timestamp))
    # make sure it's rounded up so that we import maybe more candles, but not less
    days_count = max(days_count, 1)
    if type(days_count) is float and not days_count.is_integer():
        days_count = math.ceil(days_count)
    candles_count = days_count * 1440
    start_date = jh.timestamp_to_arrow(start_timestamp).floor('day')
    for _ in range(candles_count):
        temp_start_timestamp = start_date.int_timestamp * 1000
        temp_end_timestamp = temp_start_timestamp + (backup_driver.count - 1) * 60000

        # to make sure it won't try to import candles from the future! LOL
        if temp_start_timestamp > jh.now_to_timestamp():
            break

        # prevent duplicates
        count = Candle.select().where(
            Candle.exchange == backup_driver.name,
            Candle.symbol == symbol,
            Candle.timeframe == timeframe,
            Candle.timestamp.between(temp_start_timestamp, temp_end_timestamp)
        ).count()
        already_exists = count == backup_driver.count

        if not already_exists:
            # it's today's candles if temp_end_timestamp < now
            if temp_end_timestamp > jh.now_to_timestamp():
                temp_end_timestamp = arrow.utcnow().floor('minute').int_timestamp * 1000 - 60000

            # fetch from market
            candles = backup_driver.fetch(symbol, temp_start_timestamp)

            if not len(candles):
                raise CandleNotFoundInExchange(
                    f'No candles exists in the market for this day: {jh.timestamp_to_time(temp_start_timestamp)[:10]} \n'
                    'Try another start_date'
                )

            # fill absent candles (if there's any)
            candles = _fill_absent_candles(candles, temp_start_timestamp, temp_end_timestamp)

            # store in the database
            store_candles_list(candles)

        # add as much as driver's count to the temp_start_time
        start_date = start_date.shift(minutes=backup_driver.count)

        # sleep so that the exchange won't get angry at us
        if not already_exists:
            time.sleep(backup_driver.sleep_time)

    # now try fetching from database again. Why? because we might have fetched more
    # than what's needed, but we only want as much was requested. Don't worry, the next
    # request will probably fetch from database and there won't be any waste!
    backup_candles = Candle.select(
        Candle.timestamp, Candle.open, Candle.close, Candle.high, Candle.low,
        Candle.volume
    ).where(
        Candle.exchange == backup_driver.name,
        Candle.symbol == symbol,
        Candle.timeframe == timeframe,
        Candle.timestamp.between(start_timestamp, end_timestamp)
    ).order_by(Candle.timestamp.asc()).tuples()
    already_exists = len(backup_candles) == (end_timestamp - start_timestamp) / 60_000 + 1
    if already_exists:
        # loop through them and set new ID and exchange
        for c in backup_candles:
            total_candles.append({
                'id': jh.generate_unique_id(),
                'exchange': exchange,
                'symbol': symbol,
                'timeframe': timeframe,
                'timestamp': c[0],
                'open': c[1],
                'close': c[2],
                'high': c[3],
                'low': c[4],
                'volume': c[5]
            })

        return total_candles


def _fill_absent_candles(temp_candles: List[Dict[str, Union[str, Any]]], start_timestamp: int, end_timestamp: int) -> \
        List[Dict[str, Union[str, Any]]]:
    if not temp_candles:
        raise CandleNotFoundInExchange(
            f'No candles exists in the market for this day: {jh.timestamp_to_time(start_timestamp)[:10]} \n'
            'Try another start_date'
        )

    symbol = temp_candles[0]['symbol']
    exchange = temp_candles[0]['exchange']
    candles = []
    first_candle = temp_candles[0]
    started = False
    loop_length = ((end_timestamp - start_timestamp) / 60000) + 1

    for _ in range(int(loop_length)):
        candle_for_timestamp = pydash.find(
            temp_candles, lambda c: c['timestamp'] == start_timestamp)

        if candle_for_timestamp is None:
            if started:
                last_close = candles[-1]['close']
                candles.append({
                    'id': jh.generate_unique_id(),
                    'exchange': exchange,
                    'symbol': symbol,
                    'timeframe': '1m',
                    'timestamp': start_timestamp,
                    'open': last_close,
                    'high': last_close,
                    'low': last_close,
                    'close': last_close,
                    'volume': 0
                })
            else:
                candles.append({
                    'id': jh.generate_unique_id(),
                    'exchange': exchange,
                    'symbol': symbol,
                    'timeframe': '1m',
                    'timestamp': start_timestamp,
                    'open': first_candle['open'],
                    'high': first_candle['open'],
                    'low': first_candle['open'],
                    'close': first_candle['open'],
                    'volume': 0
                })
        # candle is present
        else:
            started = True
            candles.append(candle_for_timestamp)

        start_timestamp += 60000
    return candles


def store_candles_list(candles: List[Dict]) -> None:
    from jesse.models import Candle
    for c in candles:
        if 'timeframe' not in c:
            raise Exception('Candle has no timeframe')
    Candle.insert_many(candles).on_conflict_ignore().execute()
