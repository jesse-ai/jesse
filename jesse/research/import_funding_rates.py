import arrow
import math
import time
from typing import List, Dict, Any

import jesse.helpers as jh
from jesse.exceptions import CandleNotFoundInExchange
from jesse.models import FundingRate
from jesse.modes.import_candles_mode.drivers import drivers


def import_funding_rates(exchange: str, symbol: str, start_date: str, show_progressbar: bool = True) -> str:
    """Import funding rates for a specific exchange and symbol from start_date until today."""
    try:
        start_timestamp = jh.arrow_to_timestamp(arrow.get(start_date, 'YYYY-MM-DD'))
    except Exception:
        raise ValueError(f"start_date must be a string representing a date before today. ex: 2020-01-17. You entered: {start_date}")

    today = arrow.utcnow().floor('day').int_timestamp * 1000
    if start_timestamp == today:
        raise ValueError("Today's date is not accepted. start_date must be a string a representing date BEFORE today.")
    elif start_timestamp > today:
        raise ValueError("Future's date is not accepted. start_date must be a string a representing date BEFORE today.")

    symbol = symbol.upper()

    # days to import
    until_date = arrow.utcnow().floor('day')
    start_date_arrow = arrow.get(start_timestamp / 1000)
    days_count = jh.date_diff_in_days(start_date_arrow, until_date)
    if type(days_count) is float and not days_count.is_integer():
        days_count = math.ceil(days_count)

    try:
        driver = drivers[exchange]()
    except KeyError:
        raise ValueError(f'{exchange} is not a supported exchange. Supported exchanges are: {list(drivers.keys())}')

    # each driver has a method get_funding_rate
    imported = 0
    skipped = 0

    # iterate day by day
    start_day = arrow.get(start_timestamp / 1000).floor('day')
    for _ in range(int(days_count)):
        day_start_ts = start_day.int_timestamp * 1000
        # funding rates are usually sampled less frequently but we fetch all since day_start
        try:
            data = driver.get_funding_rate(symbol, start_time=day_start_ts, limit=1000)
        except Exception as e:
            # if driver signals no data for this day, continue
            start_day = start_day.shift(days=1)
            continue

        # convert to list of (timestamp, funding_rate)
        rates = []
        for item in data:
            try:
                ts = int(item.get('fundingTime') or item.get('funding_time') or item.get('time') or 0)
                fr = float(item.get('fundingRate') or item.get('funding_rate') or item.get('rate') or 0)
            except Exception:
                continue
            rates.append((ts, fr))

        if not rates:
            skipped += 1
        else:
            # store into DB
            from jesse.research.import_candles import store_funding_rates_into_db

            import numpy as np
            arr = np.array(rates, dtype=object)
            try:
                store_funding_rates_into_db(driver.name, symbol, arr)
                imported += len(rates)
            except Exception:
                # try storing individually
                for r in rates:
                    try:
                        from jesse.research.import_candles import store_funding_rate_into_db

                        store_funding_rate_into_db(driver.name, symbol, r[1], r[0])
                        imported += 1
                    except Exception:
                        pass

        # sleep a bit to avoid rate limits
        time.sleep(driver.sleep_time if hasattr(driver, 'sleep_time') else 1)

        start_day = start_day.shift(days=1)

    success_text = f'Successfully imported funding rates since "{jh.timestamp_to_date(start_timestamp)}" until today ({imported} entries imported, {skipped} days skipped).'
    return success_text


