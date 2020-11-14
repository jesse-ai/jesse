import hashlib
import math
import os
import sys
import uuid
import random
import string
import arrow
import click
import numpy as np

CACHED_CONFIG = dict()


def app_mode():
    from jesse.config import config
    return config['app']['trading_mode']


def arrow_to_timestamp(arrow_time):
    return arrow_time.int_timestamp * 1000


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


def clean_orderbook_list(arr):
    return [[float(i[0]), float(i[1])] for i in arr]


def color(msg_text: str, msg_color: str):
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


def convert_number(old_max, old_min, new_max, new_min, old_value):
    """
    convert a number from one range (ex 40-119) to another
    range (ex 0-30) while keeping the ratio.
    """
    # validation
    if old_value > old_max or old_value < old_min:
        raise ValueError('old_value:{} must be within the range. {}-{}'.format(old_value, old_min, old_max))

    old_range = (old_max - old_min)
    new_range = (new_max - new_min)
    new_value = (((old_value - old_min) * new_range) / old_range) + new_min

    return new_value


def date_diff_in_days(date1, date2):
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


def dump_exception():
    """
    a useful debugging helper
    """
    import traceback
    print(traceback.format_exc())
    terminate_app()


def estimate_average_price(order_qty, order_price, current_qty, current_entry_price):
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


def estimate_PNL(qty, entry_price, exit_price, trade_type, trading_fee=0):
    qty = abs(qty)
    profit = qty * (exit_price - entry_price)

    if trade_type == 'short':
        profit *= -1

    fee = trading_fee * qty * (entry_price + exit_price)

    return profit - fee


def estimate_PNL_percentage(qty, entry_price, exit_price, trade_type):
    qty = abs(qty)
    profit = qty * (exit_price - entry_price)

    if trade_type == 'short':
        profit *= -1

    return (profit / (qty * entry_price)) * 100


def file_exists(path: str) -> bool:
    return os.path.isfile(path)


def generate_unique_id():
    return str(uuid.uuid4())


def get_arrow(timestamp):
    return arrow.get(timestamp / 1000)


def get_candle_source(candles: np.ndarray, source_type="close") -> np.ndarray:
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


def get_config(keys: str, default=None):
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

    if not keys in CACHED_CONFIG:
        from functools import reduce
        from jesse.config import config
        CACHED_CONFIG[keys] = reduce(lambda d, k: d.get(k, default) if isinstance(d, dict) else default,
                                     keys.split("."), config)

    return CACHED_CONFIG[keys]


def get_strategy_class(strategy_name):
    from pydoc import locate

    if is_unit_testing():
        return locate('jesse.strategies.{}.{}'.format(strategy_name, strategy_name))
    else:
        return locate('strategies.{}.{}'.format(strategy_name, strategy_name))


def insecure_hash(msg: str) -> str:
    return hashlib.md5(msg.encode()).hexdigest()


def insert_list(index: int, item, arr: list):
    """
    helper to insert an item in a Python List without removing the item
    """
    if index == -1:
        return arr + [item]

    return arr[:index] + [item] + arr[index:]


def is_backtesting():
    from jesse.config import config
    return config['app']['trading_mode'] == 'backtest'


def is_collecting_data():
    from jesse.config import config
    return config['app']['trading_mode'] == 'collect'


def is_debuggable(debug_item):
    from jesse.config import config
    return is_debugging() and config['env']['logging'][debug_item]


def is_debugging():
    from jesse.config import config
    return config['app']['debug_mode']


def is_importing_candles():
    from jesse.config import config
    return config['app']['trading_mode'] == 'import-candles'


def is_live():
    return is_livetrading() or is_paper_trading()


def is_livetrading():
    from jesse.config import config
    return config['app']['trading_mode'] == 'livetrade'


def is_optimizing():
    from jesse.config import config
    return config['app']['trading_mode'] == 'optimize'


def is_paper_trading():
    from jesse.config import config
    return config['app']['trading_mode'] == 'papertrade'


def is_test_driving():
    from jesse.config import config
    return config['app']['is_test_driving']


def is_unit_testing():
    return "pytest" in sys.modules


def key(exchange, symbol, timeframe=None):
    if timeframe is None:
        return '{}-{}'.format(exchange, symbol)

    return '{}-{}-{}'.format(exchange, symbol, timeframe)


def max_timeframe(timeframes_list):
    from jesse.enums import timeframes

    if timeframes.DAY_1 in timeframes_list:
        return timeframes.DAY_1
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
    if timeframes.MINUTE_30 in timeframes_list:
        return timeframes.MINUTE_30
    if timeframes.MINUTE_15 in timeframes_list:
        return timeframes.MINUTE_15
    if timeframes.MINUTE_5 in timeframes_list:
        return timeframes.MINUTE_5
    if timeframes.MINUTE_3 in timeframes_list:
        return timeframes.MINUTE_3

    return timeframes.MINUTE_1


def normalize(x, x_min, x_max):
    """
    Rescaling data to have values between 0 and 1
    """
    x_new = (x - x_min) / (x_max - x_min)
    return x_new


def now():
    if not (is_live() or is_collecting_data() or is_importing_candles()):
        from jesse.store import store
        return store.app.time

    return arrow.utcnow().int_timestamp * 1000


def np_shift(arr: np.ndarray, num: int, fill_value=0):
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


def opposite_side(s):
    from jesse.enums import sides

    if s == sides.BUY:
        return sides.SELL
    if s == sides.SELL:
        return sides.BUY
    raise ValueError('unsupported side')


def opposite_type(t):
    from jesse.enums import trade_types

    if t == trade_types.LONG:
        return trade_types.SHORT
    if t == trade_types.SHORT:
        return trade_types.LONG
    raise ValueError('unsupported type')


def orderbook_insertion_index_search(arr, target, ascending=True):
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


def orderbook_trim_price(p: float, ascending: bool, unit: float):
    """

    :param p:
    :param ascending:
    :param unit:
    :return:
    """
    if ascending:
        trimmed = np.ceil(p / unit) * unit
        if math.log10(unit) < 0:
            trimmed = round(trimmed, abs(int(math.log10(unit))))
        return p if trimmed == p + unit else trimmed

    trimmed = np.ceil(p / unit) * unit - unit
    if math.log10(unit) < 0:
        trimmed = round(trimmed, abs(int(math.log10(unit))))
    return p if trimmed == p - unit else trimmed


def prepare_qty(qty, side):
    if side.lower() in ('sell', 'short'):
        return -abs(qty)

    if side.lower() in ('buy', 'long'):
        return abs(qty)

    raise TypeError()


def python_version() -> float:
    return float('{}.{}'.format(sys.version_info[0], sys.version_info[1]))


def readable_duration(seconds, granularity=2):
    intervals = (
        ('weeks', 604800),  # 60 * 60 * 24 * 7
        ('days', 86400),  # 60 * 60 * 24
        ('hours', 3600),  # 60 * 60
        ('minutes', 60),
        ('seconds', 1),
    )

    result = []

    for name, count in intervals:
        value = seconds // count
        if value:
            seconds -= value * count
            if value == 1:
                name = name.rstrip('s')
            result.append("{} {}".format(value, name))
    return ', '.join(result[:granularity])


def relative_to_absolute(path: str) -> str:
    return os.path.abspath(path)


def round_price_for_live_mode(price, roundable_price):
    """
    Rounds price(s) based on exchange requirements

    :param price: float
    :param roundable_price: float | nd.array
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


def round_qty_for_live_mode(price, roundable_qty):
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

    return np.round(roundable_qty, qty_round_precision)


def secure_hash(msg: str) -> str:
    return hashlib.sha256(msg.encode()).hexdigest()


def should_execute_silently() -> bool:
    return is_optimizing() or is_unit_testing()


def side_to_type(s):
    from jesse.enums import trade_types, sides

    if s == sides.BUY:
        return trade_types.LONG
    if s == sides.SELL:
        return trade_types.SHORT
    raise ValueError


def string_after_character(string: str, character: str):
    try:
        return string.split(character, 1)[1]
    except IndexError:
        return None


def style(msg_text: str, msg_style: str):
    if msg_style is None:
        return msg_text

    if msg_style.lower() in ['bold', 'b']:
        return click.style(msg_text, bold=True)

    if msg_style.lower() in ['underline', 'u']:
        return click.style(msg_text, underline=True)

    raise ValueError('unsupported style')


def terminate_app():
    # close the database
    from jesse.services.db import close_connection
    close_connection()
    # disconnect python from the OS
    os._exit(1)


def timeframe_to_one_minutes(timeframe):
    from jesse.enums import timeframes
    from jesse.exceptions import InvalidTimeframe

    dic = {
        timeframes.MINUTE_1: 1,
        timeframes.MINUTE_3: 3,
        timeframes.MINUTE_5: 5,
        timeframes.MINUTE_15: 15,
        timeframes.MINUTE_30: 30,
        timeframes.HOUR_1: 60,
        timeframes.HOUR_2: 60 * 2,
        timeframes.HOUR_3: 60 * 3,
        timeframes.HOUR_4: 60 * 4,
        timeframes.HOUR_6: 60 * 6,
        timeframes.HOUR_8: 60 * 8,
        timeframes.DAY_1: 60 * 24,
    }

    try:
        return dic[timeframe]
    except KeyError:
        raise InvalidTimeframe(
            'Timeframe "{}" is invalid. Supported timeframes are 1m, 3m, 5m, 15m, 30m, 1h, 2h, 3h, 4h, 6h, 8h, 1D'.format(
                timeframe))


def timestamp_to_arrow(timestamp):
    return get_arrow(timestamp)


def timestamp_to_date(timestamp: int) -> str:
    return str(arrow.get(timestamp / 1000))[:10]


def timestamp_to_time(timestamp):
    return str(arrow.get(timestamp / 1000))


def today() -> int:
    """
    returns today's (beginning) timestamp

    :return: int
    """
    return arrow.utcnow().floor('day').int_timestamp * 1000


def type_to_side(t):
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


def floor_with_precision(num, precision=0):
    temp = 10 ** precision
    return math.floor(num * temp) / temp


def dashed_symbol(symbol):
    return symbol[:3] + '-' + symbol[3:]


def dashless_symbol(symbol):
    return symbol[:3] + symbol[4:]


def random_str(num_characters=8):
    return ''.join(random.choice(string.ascii_letters) for i in range(num_characters))


def base_asset(symbol: str):
    if symbol.endswith('USDT'):
        return symbol[0:len(symbol) - 4]

    if symbol.endswith('USD'):
        return symbol[0:len(symbol) - 3]

    return symbol[0:3]


def quote_asset(symbol: str):
    if symbol.endswith('USDT'):
        return 'USDT'

    if symbol.endswith('USD'):
        return 'USD'

    return symbol[3:]


def app_currency():
    from jesse.routes import router
    return quote_asset(router.routes[0].symbol)


def format_currency(num):
    return f'{num:,}'
