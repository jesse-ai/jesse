import hashlib
import math
import os
import gzip
import json
from functools import lru_cache
import random
import string
import sys
import uuid
from typing import List, Tuple, Union, Any, Optional
from pprint import pprint
import arrow
import click
import numpy
import numpy as np

CACHED_CONFIG = dict()


def app_currency() -> str:
    from jesse.info import exchange_info
    from jesse.routes import router
    if router.routes[0].exchange in exchange_info and 'settlement_currency' in exchange_info[router.routes[0].exchange]:
        return exchange_info[router.routes[0].exchange]['settlement_currency']
    else:
        return quote_asset(router.routes[0].symbol)


@lru_cache
def app_mode() -> str:
    from jesse.config import config
    return config['app']['trading_mode']


def arrow_to_timestamp(arrow_time: arrow.arrow.Arrow) -> int:
    return arrow_time.int_timestamp * 1000


def base_asset(symbol: str) -> str:
    return symbol.split('-')[0]


def binary_search(arr: list, item) -> int:
    """
    performs a simple binary search on a sorted list

    :param arr: list
    :param item:

    :return: int
    """
    from bisect import bisect_left

    i = bisect_left(arr, item)
    if i != len(arr) and arr[i] == item:
        return i
    else:
        return -1


def class_iter(Class):
    return (value for variable, value in vars(Class).items() if
            not callable(getattr(Class, variable)) and not variable.startswith("__"))


def clean_orderbook_list(arr) -> List[List[float]]:
    return [[float(i[0]), float(i[1])] for i in arr]


def color(msg_text: str, msg_color: str) -> str:
    if not msg_text:
        return ''

    if msg_color == 'black':
        return click.style(msg_text, fg='black')
    if msg_color == 'red':
        return click.style(msg_text, fg='red')
    if msg_color == 'green':
        return click.style(msg_text, fg='green')
    if msg_color == 'yellow':
        return click.style(msg_text, fg='yellow')
    if msg_color == 'blue':
        return click.style(msg_text, fg='blue')
    if msg_color == 'magenta':
        return click.style(msg_text, fg='magenta')
    if msg_color == 'cyan':
        return click.style(msg_text, fg='cyan')
    if msg_color in {'white', 'gray'}:
        return click.style(msg_text, fg='white')

    raise ValueError('unsupported color')


def convert_number(old_max: float, old_min: float, new_max: float, new_min: float, old_value: float) -> float:
    """
    convert a number from one range (ex 40-119) to another
    range (ex 0-30) while keeping the ratio.
    """
    # validation
    if old_value > old_max or old_value < old_min:
        raise ValueError(f'old_value:{old_value} must be within the range. {old_min}-{old_max}')

    old_range = (old_max - old_min)
    new_range = (new_max - new_min)
    return (((old_value - old_min) * new_range) / old_range) + new_min


def dashless_symbol(symbol: str) -> str:
    return symbol.replace("-", "")


def dashy_symbol(symbol: str) -> str:
    # if already has '-' in symbol, return symbol
    if '-' in symbol:
        return symbol

    from jesse.config import config

    for s in config['app']['considering_symbols']:
        compare_symbol = dashless_symbol(s)
        if compare_symbol == symbol:
            return s

    if symbol.endswith('EUR'):
        return symbol[:-3] + '-EUR'
    if symbol.endswith('EUT'):
        return symbol[:-3] + '-EUT'
    if symbol.endswith('GBP'):
        return symbol[:-3] + '-GBP'
    if symbol.endswith('JPY'):
        return symbol[:-3] + '-JPY'
    if symbol.endswith('MIM'):
        return symbol[:-3] + '-MIM'
    if symbol.endswith('TRY'):
        return symbol[:-3] + '-TRY'
    if symbol.endswith('USD'):
        return symbol[:-3] + '-USD'
    if symbol.endswith('UST'):
        return symbol[:-3] + '-UST'
    if symbol.endswith('USDT'):
        return symbol[:-4] + '-USDT'
    if symbol.endswith('USDC'):
        return symbol[:-4] + '-USDC'
    if symbol.endswith('USDS'):
        return symbol[:-4] + '-USDS'
    if symbol.endswith('USDP'):
        return symbol[:-4] + '-USDP'
    if symbol.endswith('USDU'):
        return symbol[:-4] + '-USDU'

    if len(symbol) > 7 and symbol.endswith('SUSDT'):
        # ex: SETHSUSDT => SETH-SUSDT
        return symbol[:-5] + '-' + symbol[-5:]

    return f"{symbol[0:3]}-{symbol[3:]}"


def date_diff_in_days(date1: arrow.arrow.Arrow, date2: arrow.arrow.Arrow) -> int:
    if type(date1) is not arrow.arrow.Arrow or type(
            date2) is not arrow.arrow.Arrow:
        raise TypeError('dates must be Arrow instances')

    dif = date2 - date1

    return abs(dif.days)


def date_to_timestamp(date: str) -> int:
    """
    converts date string into timestamp. "2015-08-01" => 1438387200000

    :param date: str
    :return: int
    """
    return arrow_to_timestamp(arrow.get(date, 'YYYY-MM-DD'))


def dna_to_hp(strategy_hp, dna: str):
    hp = {}

    for gene, h in zip(dna, strategy_hp):
        if h['type'] is int:
            decoded_gene = int(
                round(
                    convert_number(119, 40, h['max'], h['min'], ord(gene))
                )
            )
        elif h['type'] is float:
            decoded_gene = convert_number(119, 40, h['max'], h['min'], ord(gene))
        else:
            raise TypeError('Only int and float types are implemented')

        hp[h['name']] = decoded_gene
    return hp


def dump_exception() -> None:
    """
    a useful debugging helper
    """
    import traceback
    print(traceback.format_exc())
    terminate_app()


def estimate_average_price(order_qty: float, order_price: float, current_qty: float,
                           current_entry_price: float) -> float:
    """Estimates the new entry price for the position.
    This is used after having a new order and updating the currently holding position.

    Arguments:
        order_qty {float} -- qty of the new order
        order_price {float} -- price of the new order
        current_qty {float} -- current(pre-calculation) qty
        current_entry_price {float} -- current(pre-calculation) entry price

    Returns:
        float -- the new/averaged entry price
    """
    return (abs(order_qty) * order_price + abs(current_qty) *
            current_entry_price) / (abs(order_qty) + abs(current_qty))


def estimate_PNL(qty: float, entry_price: float, exit_price: float, trade_type: str, trading_fee: float = 0) -> float:
    qty = abs(qty)
    profit = qty * (exit_price - entry_price)

    if trade_type == 'short':
        profit *= -1

    fee = trading_fee * qty * (entry_price + exit_price)

    return profit - fee


def estimate_PNL_percentage(qty: float, entry_price: float, exit_price: float, trade_type: str) -> float:
    qty = abs(qty)
    profit = qty * (exit_price - entry_price)

    if trade_type == 'short':
        profit *= -1

    return (profit / (qty * entry_price)) * 100


def file_exists(path: str) -> bool:
    return os.path.isfile(path)


def clear_file(path: str) -> None:
    with open(path, 'w') as f:
        f.write('')


def make_directory(path: str) -> None:
    if not os.path.exists(path):
        os.makedirs(path)


def floor_with_precision(num: float, precision: int = 0) -> float:
    temp = 10 ** precision
    return math.floor(num * temp) / temp


def format_currency(num: float) -> str:
    return f'{num:,}'


def generate_unique_id() -> str:
    return str(uuid.uuid4())


def generate_short_unique_id() -> str:
    return str(uuid.uuid4())[:22]


def get_arrow(timestamp: int) -> arrow.arrow.Arrow:
    return timestamp_to_arrow(timestamp)


def get_candle_source(candles: np.ndarray, source_type: str = "close") -> np.ndarray:
    """
     Returns the candles corresponding the selected type.

     :param candles: np.ndarray
     :param source_type: string
     :return: np.ndarray
     """

    if source_type == "close":
        return candles[:, 2]
    elif source_type == "high":
        return candles[:, 3]
    elif source_type == "low":
        return candles[:, 4]
    elif source_type == "open":
        return candles[:, 1]
    elif source_type == "volume":
        return candles[:, 5]
    elif source_type == "hl2":
        return (candles[:, 3] + candles[:, 4]) / 2
    elif source_type == "hlc3":
        return (candles[:, 3] + candles[:, 4] + candles[:, 2]) / 3
    elif source_type == "ohlc4":
        return (candles[:, 1] + candles[:, 3] + candles[:, 4] + candles[:, 2]) / 4
    else:
        raise ValueError('type string not recognised')


def get_config(keys: str, default: Any = None) -> Any:
    """
    Gets keys as a single string separated with "." and returns value.
    Also accepts a default value so that the app would work even if
    the required config value is missing from config.py file.
    Example: get_config('env.logging.order_submission', True)

    :param keys: str
    :param default: None
    :return:
    """
    if not str:
        raise ValueError('keys string cannot be empty')

    if is_unit_testing() or keys not in CACHED_CONFIG:
        if os.environ.get(keys.upper().replace(".", "_").replace(" ", "_")) is not None:
            CACHED_CONFIG[keys] = os.environ.get(keys.upper().replace(".", "_").replace(" ", "_"))
        else:
            from functools import reduce
            from jesse.config import config
            CACHED_CONFIG[keys] = reduce(lambda d, k: d.get(k, default) if isinstance(d, dict) else default,
                                         keys.split("."), config)

    return CACHED_CONFIG[keys]


def get_store():
    from jesse.store import store
    return store


def get_strategy_class(strategy_name: str):
    from pydoc import locate

    if not is_unit_testing():
        return locate(f'strategies.{strategy_name}.{strategy_name}')
    path = sys.path[0]
    # live plugin
    if path.endswith('jesse-live'):
        strategy_dir = f'tests.strategies.{strategy_name}.{strategy_name}'
    # main framework
    else:
        strategy_dir = f'jesse.strategies.{strategy_name}.{strategy_name}'

    return locate(strategy_dir)


def insecure_hash(msg: str) -> str:
    return hashlib.md5(msg.encode()).hexdigest()


def insert_list(index: int, item, arr: list) -> list:
    """
    helper to insert an item in a Python List without removing the item
    """
    if index == -1:
        return arr + [item]

    return arr[:index] + [item] + arr[index:]


def is_backtesting() -> bool:
    from jesse.config import config
    return config['app']['trading_mode'] == 'backtest'


def is_collecting_data() -> bool:
    from jesse.config import config
    return config['app']['trading_mode'] == 'collect'


def is_debuggable(debug_item) -> bool:
    from jesse.config import config
    return is_debugging() and config['env']['logging'][debug_item]


def is_debugging() -> bool:
    from jesse.config import config
    return config['app']['debug_mode']


def is_importing_candles() -> bool:
    from jesse.config import config
    return config['app']['trading_mode'] == 'candles'


def is_live() -> bool:
    return is_livetrading() or is_paper_trading()

@lru_cache
def is_livetrading() -> bool:
    from jesse.config import config
    return config['app']['trading_mode'] == 'livetrade'

@lru_cache
def is_optimizing() -> bool:
    from jesse.config import config
    return config['app']['trading_mode'] == 'optimize'


def is_paper_trading() -> bool:
    from jesse.config import config
    return config['app']['trading_mode'] == 'papertrade'


def is_unit_testing() -> bool:
    """Returns True if the code is running by running pytest or PyCharm's test runner, False otherwise."""
    # Check if the PYTEST_CURRENT_TEST environment variable is set.
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True

    # Check if the code is being executed from the pytest command-line tool.
    script_name = os.path.basename(sys.argv[0])
    if script_name in ["pytest", "py.test"]:
        return True

    # Check if the code is being executed from PyCharm's test runner.
    if os.environ.get("PYCHARM_HOSTED"):
        return True

    # Otherwise, the code is not running by running pytest or PyCharm's test runner.
    return False


def is_valid_uuid(uuid_to_test: str, version: int = 4) -> bool:
    try:
        uuid_obj = uuid.UUID(uuid_to_test, version=version)
    except ValueError:
        return False
    return str(uuid_obj) == uuid_to_test


def key(exchange: str, symbol: str, timeframe: str = None):
    if timeframe is None:
        return f'{exchange}-{symbol}'

    return f'{exchange}-{symbol}-{timeframe}'


def max_timeframe(timeframes_list: list) -> str:
    from jesse.enums import timeframes

    if timeframes.DAY_1 in timeframes_list:
        return timeframes.DAY_1
    if timeframes.HOUR_12 in timeframes_list:
        return timeframes.HOUR_12
    if timeframes.HOUR_8 in timeframes_list:
        return timeframes.HOUR_8
    if timeframes.HOUR_6 in timeframes_list:
        return timeframes.HOUR_6
    if timeframes.HOUR_4 in timeframes_list:
        return timeframes.HOUR_4
    if timeframes.HOUR_3 in timeframes_list:
        return timeframes.HOUR_3
    if timeframes.HOUR_2 in timeframes_list:
        return timeframes.HOUR_2
    if timeframes.HOUR_1 in timeframes_list:
        return timeframes.HOUR_1
    if timeframes.MINUTE_45 in timeframes_list:
        return timeframes.MINUTE_45
    if timeframes.MINUTE_30 in timeframes_list:
        return timeframes.MINUTE_30
    if timeframes.MINUTE_15 in timeframes_list:
        return timeframes.MINUTE_15
    if timeframes.MINUTE_5 in timeframes_list:
        return timeframes.MINUTE_5
    if timeframes.MINUTE_3 in timeframes_list:
        return timeframes.MINUTE_3

    return timeframes.MINUTE_1


def normalize(x: float, x_min: float, x_max: float) -> float:
    """
    Rescaling data to have values between 0 and 1
    """
    return (x - x_min) / (x_max - x_min)


def now(force_fresh=False) -> int:
    """
    Always returns the current time in milliseconds but rounds time in matter of seconds
    """
    return now_to_timestamp(force_fresh)


def now_to_timestamp(force_fresh=False) -> int:
    if not force_fresh and (not (is_live() or is_collecting_data() or is_importing_candles())):
        from jesse.store import store
        return store.app.time

    return arrow.utcnow().int_timestamp * 1000


# for use with peewee
def now_to_datetime():
    return arrow.utcnow().datetime


def current_1m_candle_timestamp():
    return arrow.utcnow().floor('minute').int_timestamp * 1000


def np_ffill(arr: np.ndarray, axis: int = 0) -> np.ndarray:
    idx_shape = tuple([slice(None)] + [np.newaxis] * (len(arr.shape) - axis - 1))
    idx = np.where(~np.isnan(arr), np.arange(arr.shape[axis])[idx_shape], 0)
    np.maximum.accumulate(idx, axis=axis, out=idx)
    slc = [
        np.arange(k)[
            tuple(
                slice(None) if dim == i else np.newaxis
                for dim in range(len(arr.shape))
            )
        ]
        for i, k in enumerate(arr.shape)
    ]

    slc[axis] = idx
    return arr[tuple(slc)]


def np_shift(arr: np.ndarray, num: int, fill_value=0) -> np.ndarray:
    result = np.empty_like(arr)

    if num > 0:
        result[:num] = fill_value
        result[num:] = arr[:-num]
    elif num < 0:
        result[num:] = fill_value
        result[:num] = arr[-num:]
    else:
        result[:] = arr

    return result


@lru_cache
def opposite_side(s: str) -> str:
    from jesse.enums import sides

    if s == sides.BUY:
        return sides.SELL
    elif s == sides.SELL:
        return sides.BUY
    else:
        raise ValueError(f'{s} is not a valid input for side')

@lru_cache
def opposite_type(t: str) -> str:
    from jesse.enums import trade_types

    if t == trade_types.LONG:
        return trade_types.SHORT
    if t == trade_types.SHORT:
        return trade_types.LONG
    raise ValueError('unsupported type')


def orderbook_insertion_index_search(arr, target: int, ascending: bool = True) -> Tuple[bool, int]:
    target = target[0]
    lower = 0
    upper = len(arr)

    while lower < upper:
        x = lower + (upper - lower) // 2
        val = arr[x][0]
        if ascending:
            if target == val:
                return True, x
            elif target > val:
                if lower == x:
                    return False, lower + 1
                lower = x
            elif target < val:
                if lower == x:
                    return False, lower
                upper = x
        elif target == val:
            return True, x
        elif target < val:
            if lower == x:
                return False, lower + 1
            lower = x
        elif target > val:
            if lower == x:
                return False, lower
            upper = x


def orderbook_trim_price(p: float, ascending: bool, unit: float) -> float:
    if ascending:
        trimmed = np.ceil(p / unit) * unit
        if math.log10(unit) < 0:
            trimmed = round(trimmed, abs(int(math.log10(unit))))
        return p if trimmed == p + unit else trimmed

    trimmed = np.ceil(p / unit) * unit - unit
    if math.log10(unit) < 0:
        trimmed = round(trimmed, abs(int(math.log10(unit))))
    return p if trimmed == p - unit else trimmed


def prepare_qty(qty: float, side: str) -> float:
    if side.lower() in ('sell', 'short'):
        return -abs(qty)
    elif side.lower() in ('buy', 'long'):
        return abs(qty)
    elif side.lower() == 'close':
        return 0.0
    else:
        raise ValueError(f'{side} is not a valid input')


def python_version() -> tuple:
    return sys.version_info[:2]


def quote_asset(symbol: str) -> str:
    try:
        return symbol.split('-')[1]
    except IndexError:
        from jesse.exceptions import InvalidRoutes
        raise InvalidRoutes(f"The symbol format is incorrect. Correct example: 'BTC-USDT'. Yours is '{symbol}'")


def random_str(num_characters: int = 8) -> str:
    return ''.join(random.choice(string.ascii_letters) for _ in range(num_characters))


def readable_duration(seconds: int, granularity: int = 2) -> str:
    intervals = (
        ('weeks', 604800),  # 60 * 60 * 24 * 7
        ('days', 86400),  # 60 * 60 * 24
        ('hours', 3600),  # 60 * 60
        ('minutes', 60),
        ('seconds', 1),
    )

    result = []
    seconds = int(seconds)

    for name, count in intervals:
        value = seconds // count
        if value:
            seconds -= value * count
            if value == 1:
                name = name.rstrip('s')
            result.append(f"{value} {name}")
    return ', '.join(result[:granularity])


def relative_to_absolute(path: str) -> str:
    return os.path.abspath(path)


def round_or_none(x: Union[float, None], digits: int = 0) -> Optional[float]:
    """
    Rounds a number to a certain number of digits or returns None if the number is None
    """
    if x is None:
        return None
    return round(x, digits)


def round_price_for_live_mode(price, precision: int) -> Union[float, np.ndarray]:
    """
    Rounds price(s) based on exchange requirements

    :param price: float
    :param precision: int
    :return: float | nd.array
    """
    return np.round(price, precision)


def round_qty_for_live_mode(roundable_qty: float, precision: int) -> Union[float, np.ndarray]:
    """
    Rounds qty(s) based on exchange requirements

    :param roundable_qty: float | nd.array
    :param precision: int
    :return: float | nd.array
    """
    input_type = type(roundable_qty)
    # if roundable_qty is a scalar, convert to nd.array
    if not isinstance(roundable_qty, np.ndarray):
        roundable_qty = np.array([roundable_qty])

    # for qty rounding down is important to prevent InsufficenMargin
    rounded = round_decimals_down(roundable_qty, precision)

    for index, q in enumerate(rounded):
        # if the rounded value is 0, make it the minimum possible value
        if q == 0.0:
            # if the precision is bigger or equal 0, (for numbers like 2, 0.2, 0.02)
            if precision >= 0:
                rounded[index] = 1 / 10 ** precision
            else:  # for numbers like 20, 200, 2000
                raise ValueError('qty is too small')

    if input_type in [float, np.float64]:
        return float(rounded[0])
    return rounded


def round_decimals_down(number: Union[np.ndarray, float], decimals: int = 2) -> float:
    """
    Returns a value rounded down to a specific number of decimal places.
    """
    if not isinstance(decimals, int):
        raise TypeError("decimal places must be an integer")
    elif decimals == 0:
        return np.floor(number)
    elif decimals > 0:
        factor = 10 ** decimals
        return np.floor(number * factor) / factor
    elif decimals < 0:
        # for example, for decimals = -2, we want to round down to the nearest 100 if the number is 1234, we want to return 1200:
        factor = 10 ** (decimals * -1)
        return np.floor(number / factor) * factor


def same_length(bigger: np.ndarray, shorter: np.ndarray) -> np.ndarray:
    return np.concatenate((np.full((bigger.shape[0] - shorter.shape[0]), np.nan), shorter))


def secure_hash(msg: str) -> str:
    return hashlib.sha256(msg.encode()).hexdigest()


def should_execute_silently() -> bool:
    return is_optimizing() or is_unit_testing()

@lru_cache
def side_to_type(s: str) -> str:
    from jesse.enums import trade_types, sides

    # make sure string is lowercase
    s = s.lower()

    if s == sides.BUY:
        return trade_types.LONG
    if s == sides.SELL:
        return trade_types.SHORT
    raise ValueError


def string_after_character(s: str, character: str) -> str:
    try:
        return s.split(character, 1)[1]
    except IndexError:
        return None


def slice_candles(candles: np.ndarray, sequential: bool) -> np.ndarray:
    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and candles.shape[0] > warmup_candles_num:
        candles = candles[-warmup_candles_num:]
    return candles


def style(msg_text: str, msg_style: str) -> str:
    if msg_style is None:
        return msg_text

    if msg_style.lower() in ['bold', 'b']:
        return click.style(msg_text, bold=True)

    if msg_style.lower() in ['underline', 'u']:
        return click.style(msg_text, underline=True)

    raise ValueError('unsupported style')


def terminate_app() -> None:
    # close the database
    from jesse.services.db import database
    database.close_connection()
    # disconnect python from the OS
    os._exit(1)


def error(msg: str, force_print: bool = False) -> None:
    # send notifications if it's a live session
    if is_live():
        from jesse.services import logger
        logger.error(msg)
        if force_print:
            _print_error(msg)
    else:
        _print_error(msg)


def _print_error(msg: str) -> None:
    print('\n')
    print(color('========== critical error =========='.upper(), 'red'))
    print(color(msg, 'red'))
    print(color('====================================', 'red'))

@lru_cache
def timeframe_to_one_minutes(timeframe: str) -> int:
    from jesse.enums import timeframes
    from jesse.exceptions import InvalidTimeframe

    dic = {
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

    try:
        return dic[timeframe]
    except KeyError:
        all_timeframes = [timeframe for timeframe in class_iter(timeframes)]
        raise InvalidTimeframe(
            f'Timeframe "{timeframe}" is invalid. Supported timeframes are {", ".join(all_timeframes)}.')


def timestamp_to_arrow(timestamp: int) -> arrow.arrow.Arrow:
    return arrow.get(timestamp / 1000)


def timestamp_to_date(timestamp: int) -> str:
    return str(arrow.get(timestamp / 1000))[:10]


def timestamp_to_time(timestamp: int) -> str:
    return str(arrow.get(timestamp / 1000))


def timestamp_to_iso8601(timestamp: int) -> str:
    # example: 1609804800000 => '2021-01-05T00:00:00.000Z'
    return arrow.get(timestamp / 1000).isoformat()


def iso8601_to_timestamp(iso8601: str) -> int:
    # example: '2021-01-05T00:00:00.000Z' -> 1609740800000
    return int(arrow.get(iso8601, 'YYYY-MM-DDTHH:mm:ss.SSSZ').datetime.timestamp()) * 1000


def today_to_timestamp() -> int:
    """
    returns today's (beginning) timestamp

    :return: int
    """
    return arrow.utcnow().floor('day').int_timestamp * 1000


@lru_cache
def type_to_side(t: str) -> str:
    from jesse.enums import trade_types, sides

    if t == trade_types.LONG:
        return sides.BUY
    if t == trade_types.SHORT:
        return sides.SELL
    raise ValueError(f'unsupported type: "{t}". Only "long" and "short" are supported.')


def unique_list(arr) -> list:
    """
    returns a unique version of the list while keeping its order
    :param arr: list | tuple
    :return: list
    """
    seen = set()
    seen_add = seen.add
    return [x for x in arr if not (x in seen or seen_add(x))]


def closing_side(position_type: str) -> str:
    if position_type.lower() == 'long':
        return 'sell'
    elif position_type.lower() == 'short':
        return 'buy'
    else:
        raise ValueError(f'Value entered for position_type ({position_type}) is not valid')


def merge_dicts(d1: dict, d2: dict) -> dict:
    """
    Merges nested dictionaries

    :param d1: dict
    :param d2: dict
    :return: dict
    """

    def inner(dict1, dict2):
        for k in set(dict1.keys()).union(dict2.keys()):
            if k in dict1 and k in dict2:
                if isinstance(dict1[k], dict) and isinstance(dict2[k], dict):
                    yield k, dict(merge_dicts(dict1[k], dict2[k]))
                else:
                    yield k, dict2[k]
            elif k in dict1:
                yield k, dict1[k]
            else:
                yield k, dict2[k]

    return dict(inner(d1, d2))


def computer_name():
    import platform
    return platform.node()


def validate_response(response):
    if response.status_code != 200:
        err_msg = f"[{response.status_code}]: {response.json()['message']}\nPlease contact us at support@jesse.trade if this is unexpected."

        if response.status_code not in [401, 403]:
            raise ConnectionError(err_msg)
        error(err_msg, force_print=True)
        terminate_app()


def get_session_id():
    from jesse.store import store
    if store.app.session_id == '':
        store.app.session_id = generate_unique_id()
    return store.app.session_id


def get_pid():
    return os.getpid()


def is_jesse_project():
    ls = os.listdir('.')
    return 'strategies' in ls and 'storage' in ls


def dd(item):
    """
    Dump and Die but pretty: used for debugging when developing Jesse
    """
    dump(item)
    terminate_app()


def dump(*item):
    """
    Dump object in pretty format: used for debugging when developing Jesse
    """
    if len(item) == 1:
        item = item[0]

    print(
        color('\n========= Debugging Value =========='.upper(), 'yellow')
    )

    pprint(item)

    print(
        color('====================================\n', 'yellow')
    )


def float_or_none(item):
    """
    Return the float of the value if it's not None
    """
    if item is None or item == '':
        return None
    else:
        return float(item)


def str_or_none(item, encoding='utf-8'):
    """
    Return the str of the value if it's not None
    """
    if item is None:
        return None
    else:
        # return item if it's str, if not, decode it using encoding
        if isinstance(item, str):
            return item

        if type(item) == numpy.float64:
            return str(item)

        try:
            return str(item, encoding)
        except TypeError:
            return str(item)


def cpu_cores_count():
    from multiprocessing import cpu_count
    return cpu_count()


# a function that converts name to env_name. Example: 'Testnet Binance Futures' into 'TESTNET_BINANCE_FUTURES'
def convert_to_env_name(name: str) -> str:
    return name.replace(' ', '_').upper()


def is_notebook():
    try:
        shell = get_ipython().__class__.__name__
        # Jupyter notebook or qtconsole
        if shell == 'ZMQInteractiveShell':
            return True
        elif shell == 'TerminalInteractiveShell':
            # Terminal running IPython
            return False
        else:
            # Other type (?)
            return False
    except NameError:
        # Probably standard Python interpreter
        return False


def get_os() -> str:
    import platform
    if platform.system() == 'Darwin':
        return 'mac'
    elif platform.system() == 'Linux':
        return 'linux'
    elif platform.system() == 'Windows':
        return 'windows'
    else:
        raise NotImplementedError(f'Unsupported OS: "{platform.system()}"')


# a function that returns boolean whether or not the code is being executed inside a docker container
def is_docker() -> bool:
    import os
    return os.path.exists('/.dockerenv')


def clear_output():
    if is_notebook():
        from IPython.display import clear_output
        clear_output(wait=True)
    else:
        click.clear()


def get_class_name(cls):
    # if it's a string, return it
    if isinstance(cls, str):
        return cls
    # else, return the class name
    return cls.__name__


def next_candle_timestamp(candle: np.ndarray, timeframe: str) -> int:
    return candle[0] + timeframe_to_one_minutes(timeframe) * 60_000


def get_candle_start_timestamp_based_on_timeframe(timeframe: str, num_candles_to_fetch: int) -> int:
    one_min_count = timeframe_to_one_minutes(timeframe)
    finish_date = now(force_fresh=True)
    return finish_date - (num_candles_to_fetch * one_min_count * 60_000)


def is_price_near(order_price, price_to_compare, percentage_threshold=0.0001):
    """
    Check if the given order price is near the specified price.
    Default percentage_threshold is 0.01% (0.0001)
    We calculate percentage difference between the two prices rounded to 4 decimal places, 
    so low-priced orders can be properly compared within 0.01% range.
    """
    return round(abs(1 - (order_price / price_to_compare)), 4) <= percentage_threshold


def gzip_compress(data):
    """Compress data using gzip."""
    json_data = json.dumps(data).encode('utf-8')
    # Compress the JSON string
    return gzip.compress(json_data)
