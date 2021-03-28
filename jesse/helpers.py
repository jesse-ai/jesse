import hashlib
import math
import os
import random
import string
import sys
import uuid
from typing import List, Tuple, Union, Any

import arrow
import click
import numpy as np

CACHED_CONFIG = dict()


def app_currency() -> str:
    from jesse.routes import router
    return quote_asset(router.routes[0].symbol)


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
    if msg_color in ['white', 'gray']:
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
    new_value = (((old_value - old_min) * new_range) / old_range) + new_min

    return new_value


def dashless_symbol(symbol: str) -> str:
    return symbol.replace("-", "")


def dashy_symbol(symbol: str) -> str:
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


def floor_with_precision(num: float, precision: int = 0) -> float:
    temp = 10 ** precision
    return math.floor(num * temp) / temp


def format_currency(num: float) -> str:
    return f'{num:,}'


def generate_unique_id() -> str:
    return str(uuid.uuid4())


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

    if is_unit_testing() or not keys in CACHED_CONFIG:
        if os.environ.get(keys.upper().replace(".", "_")) is not None:
            CACHED_CONFIG[keys] = os.environ.get(keys.upper().replace(".", "_"))
        else:
            from functools import reduce
            from jesse.config import config
            CACHED_CONFIG[keys] = reduce(lambda d, k: d.get(k, default) if isinstance(d, dict) else default,
                                         keys.split("."), config)

    return CACHED_CONFIG[keys]


def get_strategy_class(strategy_name: str):
    from pydoc import locate

    if is_unit_testing():
        return locate(f'jesse.strategies.{strategy_name}.{strategy_name}')
    else:
        return locate(f'strategies.{strategy_name}.{strategy_name}')


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
    return config['app']['trading_mode'] == 'import-candles'


def is_live() -> bool:
    return is_livetrading() or is_paper_trading()


def is_livetrading() -> bool:
    from jesse.config import config
    return config['app']['trading_mode'] == 'livetrade'


def is_optimizing() -> bool:
    from jesse.config import config
    return config['app']['trading_mode'] == 'optimize'


def is_paper_trading() -> bool:
    from jesse.config import config
    return config['app']['trading_mode'] == 'papertrade'


def is_test_driving() -> bool:
    from jesse.config import config
    return config['app']['is_test_driving']


def is_unit_testing() -> bool:
    return "pytest" in sys.modules


def is_valid_uuid(uuid_to_test, version: int = 4) -> bool:
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

    if timeframes.WEEK_1 in timeframes_list:
        return timeframes.WEEK_1
    if timeframes.DAY_3 in timeframes_list:
        return timeframes.DAY_3
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
    x_new = (x - x_min) / (x_max - x_min)
    return x_new


def now() -> int:
    return now_to_timestamp()


def now_to_timestamp() -> int:
    if not (is_live() or is_collecting_data() or is_importing_candles()):
        from jesse.store import store
        return store.app.time

    return arrow.utcnow().int_timestamp * 1000


def np_ffill(arr: np.ndarray, axis: int = 0) -> np.ndarray:
    idx_shape = tuple([slice(None)] + [np.newaxis] * (len(arr.shape) - axis - 1))
    idx = np.where(~np.isnan(arr), np.arange(arr.shape[axis])[idx_shape], 0)
    np.maximum.accumulate(idx, axis=axis, out=idx)
    slc = [np.arange(k)[tuple([slice(None) if dim == i else np.newaxis
                               for dim in range(len(arr.shape))])]
           for i, k in enumerate(arr.shape)]
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


def opposite_side(s: str) -> str:
    from jesse.enums import sides

    if s == sides.BUY:
        return sides.SELL
    if s == sides.SELL:
        return sides.BUY
    raise ValueError('unsupported side')


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

    if ascending:
        while lower < upper:
            x = lower + (upper - lower) // 2
            val = arr[x][0]
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
    else:
        while lower < upper:
            x = lower + (upper - lower) // 2
            val = arr[x][0]
            if target == val:
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

    if side.lower() in ('buy', 'long'):
        return abs(qty)

    raise TypeError()


def python_version() -> float:
    return float(f'{sys.version_info[0]}.{sys.version_info[1]}')


def quote_asset(symbol: str) -> str:
    try:
        return symbol.split('-')[1]
    except IndexError:
        from jesse.exceptions import InvalidRoutes
        raise InvalidRoutes(f"The symbol format is incorrect. Correct example: 'BTC-USDT'. Yours is '{symbol}'")


def random_str(num_characters: int = 8) -> str:
    return ''.join(random.choice(string.ascii_letters) for i in range(num_characters))


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


def round_price_for_live_mode(price: float, roundable_price: float) -> Union[float, np.ndarray]:
    """
    Rounds price(s) based on exchange requirements

    :param price: float
    :param roundable_price: float
    :return: float | nd.array
    """
    n = int(math.log10(price))

    if price < 1:
        price_round_precision = abs(n - 4)
    else:
        price_round_precision = 3 - n
        if price_round_precision < 0:
            price_round_precision = 0

    return np.round(roundable_price, price_round_precision)


def round_qty_for_live_mode(price: float, roundable_qty: float) -> Union[float, np.ndarray]:
    """
    Rounds qty(s) based on exchange requirements

    :param price: float
    :param roundable_qty: float | nd.array
    :return: float | nd.array
    """
    n = int(math.log10(price))

    if price < 1:
        qty_round_precision = 0
    else:
        qty_round_precision = n + 1
        if qty_round_precision > 3:
            qty_round_precision = 3
    rounded = np.round(roundable_qty, qty_round_precision)

    for index, q in enumerate(rounded):
        if q == 0.0:
            rounded[index] = 0.001

    return rounded


def same_length(bigger: np.ndarray, shorter: np.ndarray) -> np.ndarray:
    return np.concatenate((np.full((bigger.shape[0] - shorter.shape[0]), np.nan), shorter))


def secure_hash(msg: str) -> str:
    return hashlib.sha256(msg.encode()).hexdigest()


def should_execute_silently() -> bool:
    return is_optimizing() or is_unit_testing()


def side_to_type(s: str) -> str:
    from jesse.enums import trade_types, sides

    if s == sides.BUY:
        return trade_types.LONG
    if s == sides.SELL:
        return trade_types.SHORT
    raise ValueError


def string_after_character(string: str, character: str) -> str:
    try:
        return string.split(character, 1)[1]
    except IndexError:
        return None


def slice_candles(candles: np.ndarray, sequential: bool) -> np.ndarray:
    warmup_candles_num = get_config('env.data.warmup_candles_num', 240)
    if not sequential and len(candles) > warmup_candles_num:
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
    from jesse.services.db import close_connection
    close_connection()
    # disconnect python from the OS
    os._exit(1)


def error(msg: str, force_print: bool = False) -> None:
    # send notifications if it's a live session
    if is_live():
        from jesse.services import logger
        logger.error(msg)
        if force_print:
            print(color(msg, 'red'))
    else:
        print(color(msg, 'red'))


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


def today_to_timestamp() -> int:
    """
    returns today's (beginning) timestamp

    :return: int
    """
    return arrow.utcnow().floor('day').int_timestamp * 1000


def type_to_side(t: str) -> str:
    from jesse.enums import trade_types, sides

    if t == trade_types.LONG:
        return sides.BUY
    if t == trade_types.SHORT:
        return sides.SELL
    raise ValueError


def unique_list(arr) -> list:
    """
    returns a unique version of the list while keeping its order
    :param arr: list | tuple
    :return: list
    """
    seen = set()
    seen_add = seen.add
    return [x for x in arr if not (x in seen or seen_add(x))]
