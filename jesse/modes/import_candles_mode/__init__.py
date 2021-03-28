import math
import threading
import time
from typing import Dict, List, Any, Union

import arrow
import click
import pydash

import jesse.helpers as jh
from jesse.exceptions import CandleNotFoundInExchange
from jesse.models import Candle
from jesse.modes.import_candles_mode.drivers import drivers
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange


def run(exchange: str, symbol: str, start_date_str: str, skip_confirmation: bool = False) -> None:
    try:
        start_timestamp = jh.arrow_to_timestamp(arrow.get(start_date_str, 'YYYY-MM-DD'))
    except:
        raise ValueError('start_date must be a string representing a date before today. ex: 2020-01-17')

    # more start_date validations
    today = arrow.utcnow().floor('day').int_timestamp * 1000
    if start_timestamp == today:
        raise ValueError("Today's date is not accepted. start_date must be a string a representing date BEFORE today.")
    elif start_timestamp > today:
        raise ValueError("Future's date is not accepted. start_date must be a string a representing date BEFORE today.")

    # We just call this to throw a exception in case of a symbol without dash
    jh.quote_asset(symbol)

    click.clear()
    symbol = symbol.upper()

    until_date = arrow.utcnow().floor('day')
    start_date = arrow.get(start_timestamp / 1000)
    days_count = jh.date_diff_in_days(start_date, until_date)
    candles_count = days_count * 1440
    exchange = exchange.title()

    try:
        driver: CandleExchange = drivers[exchange]()
    except KeyError:
        raise ValueError(f'{exchange} is not a supported exchange')

    loop_length = int(candles_count / driver.count) + 1
    # ask for confirmation
    if not skip_confirmation:
        click.confirm(
            f'Importing {days_count} days candles from "{exchange}" for "{symbol}". Duplicates will be skipped. All good?', abort=True, default=True)

    with click.progressbar(length=loop_length, label='Importing candles...') as progressbar:
        for _ in range(candles_count):
            temp_start_timestamp = start_date.int_timestamp * 1000
            temp_end_timestamp = temp_start_timestamp + (driver.count - 1) * 60000

            # to make sure it won't try to import candles from the future! LOL
            if temp_start_timestamp > jh.now_to_timestamp():
                break

            # prevent duplicates calls to boost performance
            count = Candle.select().where(
                Candle.timestamp.between(temp_start_timestamp, temp_end_timestamp),
                Candle.symbol == symbol,
                Candle.exchange == exchange
            ).count()
            already_exists = count == driver.count

            if not already_exists:
                # it's today's candles if temp_end_timestamp < now
                if temp_end_timestamp > jh.now_to_timestamp():
                    temp_end_timestamp = arrow.utcnow().floor('minute').int_timestamp * 1000 - 60000

                # fetch from market
                candles = driver.fetch(symbol, temp_start_timestamp)

                if not len(candles):
                    click.clear()
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
                        driver.init_backup_exchange()
                        if driver.backup_exchange is not None:
                            candles = _get_candles_from_backup_exchange(
                                exchange, driver.backup_exchange, symbol, temp_start_timestamp, temp_end_timestamp
                            )

                    else:
                        if not skip_confirmation:
                            print(jh.color(f'No candle exists in the market for {jh.timestamp_to_time(temp_start_timestamp)[:10]}\n', 'yellow'))
                            click.confirm(
                                f'First present candle is since {jh.timestamp_to_time(first_existing_timestamp)[:10]}. Would you like to continue?', abort=True, default=True)

                        run(exchange, symbol, jh.timestamp_to_time(first_existing_timestamp)[:10], True)
                        return

                # fill absent candles (if there's any)
                candles = _fill_absent_candles(candles, temp_start_timestamp, temp_end_timestamp)

                # store in the database
                if skip_confirmation:
                    _insert_to_database(candles)
                else:
                    threading.Thread(target=_insert_to_database, args=[candles]).start()

            # add as much as driver's count to the temp_start_time
            start_date = start_date.shift(minutes=driver.count)

            progressbar.update(1)

            # sleep so that the exchange won't get angry at us
            if not already_exists:
                time.sleep(driver.sleep_time)


def _get_candles_from_backup_exchange(exchange: str, backup_driver: CandleExchange, symbol: str, start_timestamp: int,
                                      end_timestamp: int) -> List[Dict[str, Union[str, Any]]]:
    total_candles = []
    # try fetching from database first
    backup_candles = Candle.select(
        Candle.timestamp, Candle.open, Candle.close, Candle.high, Candle.low,
        Candle.volume
    ).where(
        Candle.timestamp.between(start_timestamp, end_timestamp),
        Candle.exchange == backup_driver.name,
        Candle.symbol == symbol).order_by(Candle.timestamp.asc()).tuples()
    already_exists = len(backup_candles) == (end_timestamp - start_timestamp) / 60_000 + 1
    if already_exists:
        # loop through them and set new ID and exchange
        for c in backup_candles:
            total_candles.append({
                'id': jh.generate_unique_id(),
                'symbol': symbol,
                'exchange': exchange,
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
    if days_count < 1:
        days_count = 1
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
            Candle.timestamp.between(temp_start_timestamp, temp_end_timestamp),
            Candle.symbol == symbol,
            Candle.exchange == backup_driver.name
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
            _insert_to_database(candles)

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
        Candle.timestamp.between(start_timestamp, end_timestamp),
        Candle.exchange == backup_driver.name,
        Candle.symbol == symbol).order_by(Candle.timestamp.asc()).tuples()
    already_exists = len(backup_candles) == (end_timestamp - start_timestamp) / 60_000 + 1
    if already_exists:
        # loop through them and set new ID and exchange
        for c in backup_candles:
            total_candles.append({
                'id': jh.generate_unique_id(),
                'symbol': symbol,
                'exchange': exchange,
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
    if len(temp_candles) == 0:
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

    i = 0
    while i < loop_length:
        candle_for_timestamp = pydash.find(
            temp_candles, lambda c: c['timestamp'] == start_timestamp)

        if candle_for_timestamp is None:
            if started:
                last_close = candles[-1]['close']
                candles.append({
                    'id': jh.generate_unique_id(),
                    'symbol': symbol,
                    'exchange': exchange,
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
                    'symbol': symbol,
                    'exchange': exchange,
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
        i += 1

    return candles


def _insert_to_database(candles: List[Dict[str, Union[str, Any]]]) -> None:
    Candle.insert_many(candles).on_conflict_ignore().execute()
