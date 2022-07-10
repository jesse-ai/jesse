import os

import arrow
import numpy as np
import pytest

import jesse.helpers as jh


def test_app_currency():
    from jesse.routes import router
    from jesse.enums import exchanges, timeframes
    router.initiate(
        [{'exchange': exchanges.BITFINEX_SPOT, 'symbol': 'ETH-USD', 'timeframe': timeframes.HOUR_3, 'strategy': 'Test19'}])
    assert jh.app_currency() == 'USD'


def test_app_mode():
    assert jh.app_mode() == 'backtest'


def test_arrow_to_timestamp():
    arrow_time = arrow.get('2015-08-01')
    assert jh.arrow_to_timestamp(arrow_time) == 1438387200000


def test_base_asset():
    assert jh.base_asset('BTC-USDT') == 'BTC'
    assert jh.base_asset('BTC-USD') == 'BTC'
    assert jh.base_asset('DEFI-USDT') == 'DEFI'
    assert jh.base_asset('DEFI-USD') == 'DEFI'


def test_binary_search():
    arr = [0, 11, 22, 33, 44, 54, 55]

    assert jh.binary_search(arr, 22) == 2
    assert jh.binary_search(arr, 222) == -1


def test_clean_orderbook_list():
    assert np.array_equal(
        jh.clean_orderbook_list([
            ['10', '11'],
            ['11', '14'],
            ['12', '13'],
            ['13', '133'],
            ['14', '12'],
        ]),
        [
            [10, 11],
            [11, 14],
            [12, 13],
            [13, 133],
            [14, 12],
        ]
    )


def test_color():
    msg_text = 'msg'
    msg_color = 'black'
    assert jh.color(msg_text, msg_color) == '\x1b[30mmsg\x1b[0m'


def test_convert_number():
    old_max = 119
    old_min = 40
    new_max = 4.0
    new_min = 0.5
    old_value = 41

    assert jh.convert_number(old_max, old_min, new_max, new_min, old_value) == 0.5443037974683544


def test_dashless_symbol():
    assert jh.dashless_symbol('BTC-USD') == 'BTCUSD'
    assert jh.dashless_symbol('BTC-USDT') == 'BTCUSDT'
    assert jh.dashless_symbol('1INCH-USDT') == '1INCHUSDT'
    assert jh.dashless_symbol('SC-USDT') == 'SCUSDT'

    # make sure that it works even if it's already dashless
    assert jh.dashless_symbol('BTCUSDT') == 'BTCUSDT'


def test_dashy_symbol():
    assert jh.dashy_symbol('BTCUSD') == 'BTC-USD'
    assert jh.dashy_symbol('BTCUSDT') == 'BTC-USDT'
    assert jh.dashy_symbol('BTC-USDT') == 'BTC-USDT'


def test_date_diff_in_days():
    date_1 = arrow.get('2015-12-23 18:40:48', 'YYYY-MM-DD HH:mm:ss')
    date_2 = arrow.get('2017-11-15 13:18:20', 'YYYY-MM-DD HH:mm:ss')
    diff = jh.date_diff_in_days(date_1, date_2)
    assert diff == 692


def test_date_to_timestamp():
    assert jh.date_to_timestamp('2015-08-01') == 1438387200000


def test_dna_to_hp():
    strategy_hp = [
        {'name': 'hp1', 'type': float, 'min': 0.01, 'max': 1.0, 'default': 0.09},
        {'name': 'hp2', 'type': int, 'min': 1, 'max': 10, 'default': 2},
    ]
    dna = ".6"
    assert jh.dna_to_hp(strategy_hp, dna) == {'hp1': 0.08518987341772151, 'hp2': 3}


def test_dump_exception():
    # uses database, which is not existing during testing
    pass


def test_estimate_average_price():
    assert jh.estimate_average_price(100, 7200, 0, 0) == 7200

    with pytest.raises(TypeError):
        jh.estimate_average_price(100, 7200, 0, None)
        jh.estimate_average_price(100, 7200, None, 0)
        jh.estimate_average_price(100, None, 0, 0)
        jh.estimate_average_price(None, 7200, 0, 0)


def test_estimate_PNL():
    # profit
    assert jh.estimate_PNL(2, 50, 60, 'long') == 20
    assert jh.estimate_PNL(2, 60, 50, 'short') == 20

    # loss
    assert jh.estimate_PNL(2, 50, 60, 'short') == -20
    assert jh.estimate_PNL(2, 60, 50, 'long') == -20

    # profit with fee
    assert jh.estimate_PNL(1, 10, 20, 'long', 0.002) == 9.94
    # loss with fee
    assert jh.estimate_PNL(1, 10, 20, 'short', 0.002) == -10.06

    with pytest.raises(TypeError):
        jh.estimate_PNL(1, 200, 220, 1)
        jh.estimate_PNL(1, 200, 'invalid_input', 'short')
        jh.estimate_PNL(1, 'invalid_input', 220, 'short')
        jh.estimate_PNL('invalid_input', 200, 220, 'short')


def test_estimate_PNL_percentage():
    # profit
    assert jh.estimate_PNL_percentage(1, 200, 220, 'long') == 10
    assert jh.estimate_PNL_percentage(1, 200, 180, 'short') == 10

    # loss
    assert jh.estimate_PNL_percentage(1, 200, 180, 'long') == -10
    assert jh.estimate_PNL_percentage(1, 200, 220, 'short') == -10

    with pytest.raises(TypeError):
        jh.estimate_PNL_percentage(1, 200, 220, 1)
        jh.estimate_PNL_percentage(1, 200, 'invalid_input', 'short')
        jh.estimate_PNL_percentage(1, 'invalid_input', 220, 'short')
        jh.estimate_PNL_percentage('invalid_input', 200, 220, 'short')


def test_file_exists():
    assert jh.file_exists('tests/test_helpers.py') is True


def test_floor_with_precision():
    assert jh.floor_with_precision(1.123) == 1
    assert jh.floor_with_precision(1.123, 1) == 1.1
    assert jh.floor_with_precision(1.123, 2) == 1.12
    assert jh.floor_with_precision(1.123, 3) == 1.123
    assert jh.floor_with_precision(1.123, 4) == 1.123


def test_format_currency():
    assert jh.format_currency(100_000_000) == '100,000,000'
    assert jh.format_currency(100_000_000.23) == '100,000,000.23'


def test_generate_unique_id():
    assert jh.is_valid_uuid(jh.generate_unique_id()) is True
    assert jh.is_valid_uuid('asdfasdfasdfasfsadfsd') is False


def test_get_candle_source():
    candle = np.array(([1575547200000, 146.51, 147.03, 149.02, 146.51, 64788.46651],
                       [1553817660000, 4092.56783507, 4092.5, 4092.56783507, 4092.5, 9.0847059]))
    close = jh.get_candle_source(candle, source_type="close")
    assert close[-1] == 4092.5
    high = jh.get_candle_source(candle, source_type="high")
    assert high[-1] == 4092.56783507
    low = jh.get_candle_source(candle, source_type="low")
    assert low[-1] == 4092.5
    open = jh.get_candle_source(candle, source_type="open")
    assert open[-1] == 4092.56783507
    volume = jh.get_candle_source(candle, source_type="volume")
    assert volume[-1] == 9.0847059
    hl2 = jh.get_candle_source(candle, source_type="hl2")
    assert hl2[-1] == 4092.533917535
    hlc3 = jh.get_candle_source(candle, source_type="hlc3")
    assert hlc3[-1] == 4092.52261169
    ohlc4 = jh.get_candle_source(candle, source_type="ohlc4")
    assert ohlc4[-1] == 4092.533917535


def test_get_config(monkeypatch):
    # assert when config does NOT exist (must return passed default)
    assert jh.get_config('aaaaaaa', 2020) == 2020
    # assert when config does exist
    assert jh.get_config('env.logging.order_submission', 2020) is True
    # assert env is took
    monkeypatch.setenv("ENV_DATABASES_POSTGRES_HOST", "db")
    assert jh.get_config('env.databases.postgres_host', 'default') == 'db'
    monkeypatch.delenv("ENV_DATABASES_POSTGRES_HOST")
    # assert env is took with space
    monkeypatch.setenv("ENV_EXCHANGES_BINANCE_FUTURES_SETTLEMENT_CURRENCY", 'BUSD')
    assert jh.get_config('env.exchanges.Binance Futures.settlement_currency', 'USDT') == 'BUSD'
    monkeypatch.delenv("ENV_EXCHANGES_BINANCE_FUTURES_SETTLEMENT_CURRENCY")


def test_get_strategy_class():
    from jesse.strategies import Strategy
    assert issubclass(jh.get_strategy_class("Test01"), Strategy)


def test_insecure_hash():
    assert jh.insecure_hash("test") == "098f6bcd4621d373cade4e832627b4f6"


def test_insert_list():
    my_list = [0, 1, 2, 3]

    assert jh.insert_list(2, 22, my_list) == [0, 1, 22, 2, 3]
    assert jh.insert_list(0, 22, my_list) == [22, 0, 1, 2, 3]
    assert jh.insert_list(-1, 22, my_list) == [0, 1, 2, 3, 22]

    # assert list is untouched
    assert my_list == [0, 1, 2, 3]


def test_is_backtesting():
    assert jh.is_backtesting() is True


def test_is_collecting_data():
    assert jh.is_collecting_data() is False


def test_is_debuggable():
    debug_item = 'order_submission'
    assert jh.is_debuggable(debug_item) is False


def test_is_debugging():
    assert jh.is_debugging() is False


def test_is_importing_candles():
    assert jh.is_importing_candles() is False


def test_is_live():
    assert jh.is_live() is False


def test_is_livetrading():
    assert jh.is_livetrading() is False


def test_is_optimizing():
    assert jh.is_optimizing() is False


def test_is_paper_trading():
    assert jh.is_paper_trading() is False


def test_is_unit_testing():
    assert jh.is_unit_testing() is True


def test_key():
    exchange = "Exchange"
    symbol = "BTC-USD"
    timeframe = "6h"
    assert jh.key(exchange, symbol) == "Exchange-BTC-USD"
    assert jh.key(exchange, symbol, timeframe) == "Exchange-BTC-USD-6h"


def test_max_timeframe():
    assert jh.max_timeframe(['1m', '3m']) == '3m'
    assert jh.max_timeframe(['3m', '5m']) == '5m'
    assert jh.max_timeframe(['15m', '5m']) == '15m'
    assert jh.max_timeframe(['30m', '15m']) == '30m'
    assert jh.max_timeframe(['30m', '1h']) == '1h'
    assert jh.max_timeframe(['1h', '2h']) == '2h'
    assert jh.max_timeframe(['2h', '3h']) == '3h'
    assert jh.max_timeframe(['4h', '3h']) == '4h'
    assert jh.max_timeframe(['6h', '4h']) == '6h'
    assert jh.max_timeframe(['8h', '4h']) == '8h'
    assert jh.max_timeframe(['6h', '1D']) == '1D'


def test_normalize():
    assert jh.normalize(10, 0, 20) == 0.5
    assert jh.normalize(20, 0, 20) == 1
    assert jh.normalize(0, 0, 20) == 0


def test_now_to_timestamp():
    from jesse.store import store
    assert jh.now_to_timestamp() == store.app.time


def test_np_ffill():
    arr = np.array([0, 1, np.nan, np.nan])
    res = jh.np_ffill(arr)
    expected = np.array([0, 1, 1, 1])

    np.equal(res, expected)


def test_np_shift():
    arr = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9])
    res = jh.np_shift(arr, -3)
    expected = np.array([4, 5, 6, 7, 8, 9, 0, 0, 0])

    np.equal(res, expected)


def test_opposite_side():
    assert jh.opposite_side('buy') == 'sell'
    assert jh.opposite_side('sell') == 'buy'


def test_opposite_type():
    assert jh.opposite_type('long') == 'short'
    assert jh.opposite_type('short') == 'long'


def test_orderbook_insertion_index_search():
    ascending_arr = [
        [10, 232],
        [11, 33232],
        [12, 233],
        [33, 21323],
        [44, 23123],
        [55, 2321],
        [66, 23213]
    ]

    assert jh.orderbook_insertion_index_search(ascending_arr, [7, 2]) == (False, 0)
    assert jh.orderbook_insertion_index_search(ascending_arr, [2, 2]) == (False, 0)
    assert jh.orderbook_insertion_index_search(ascending_arr, [32, 2]) == (False, 3)
    assert jh.orderbook_insertion_index_search(ascending_arr, [34, 2]) == (False, 4)
    assert jh.orderbook_insertion_index_search(ascending_arr, [1, 2]) == (False, 0)
    assert jh.orderbook_insertion_index_search(ascending_arr, [66, 2]) == (True, 6)
    assert jh.orderbook_insertion_index_search(ascending_arr, [77, 2]) == (False, 7)

    descending_arr = [
        [66, 232],
        [55, 33232],
        [44, 233],
        [33, 21323],
        [2, 23123],
    ]

    assert jh.orderbook_insertion_index_search(descending_arr, [77, 2], ascending=False) == (False, 0)
    assert jh.orderbook_insertion_index_search(descending_arr, [2, 2], ascending=False) == (True, 4)
    assert jh.orderbook_insertion_index_search(descending_arr, [65, 2], ascending=False) == (False, 1)
    assert jh.orderbook_insertion_index_search(descending_arr, [1, 2], ascending=False) == (False, 5)


def test_orderbook_trim_price():
    # bids
    assert jh.orderbook_trim_price(101.12, False, .1) == 101.1
    assert jh.orderbook_trim_price(101.1, False, .1) == 101.1

    assert jh.orderbook_trim_price(10.12, False, .01) == 10.12
    assert jh.orderbook_trim_price(10.1, False, .01) == 10.1
    assert jh.orderbook_trim_price(10.122, False, .01) == 10.12
    assert jh.orderbook_trim_price(1.1223, False, .001) == 1.122

    # asks
    assert jh.orderbook_trim_price(101.12, True, .1) == 101.2
    assert jh.orderbook_trim_price(101.1, True, .1) == 101.1
    assert jh.orderbook_trim_price(10.12, True, .01) == 10.12
    assert jh.orderbook_trim_price(10.122, True, .01) == 10.13
    assert jh.orderbook_trim_price(1.1223, True, .001) == 1.123


def test_prepare_qty():
    assert jh.prepare_qty(10, 'sell') == -10
    assert jh.prepare_qty(-10, 'buy') == 10
    assert jh.prepare_qty(0, 'close') == 0.0

    with pytest.raises(ValueError):
        jh.prepare_qty(-10, 'invalid_input')


def test_python_version():
    import sys
    assert jh.python_version() == sys.version_info[:2]


def test_quote_asset():
    assert jh.quote_asset('BTC-USDT') == 'USDT'
    assert jh.quote_asset('DEFI-USDT') == 'USDT'
    assert jh.quote_asset('DEFI-EUR') == 'EUR'


def test_random_str():
    assert len(jh.random_str(10)) == 10


def test_readable_duration():
    assert jh.readable_duration(604312) == "6 days, 23 hours"


def test_relative_to_absolute():
    from pathlib import Path
    assert jh.relative_to_absolute("tests/test_helpers.py") == str(Path(__file__).absolute())


def test_round_price_for_live_mode():
    np.testing.assert_equal(
        jh.round_price_for_live_mode(np.array([0.0003209123456, 0.0004209123456]), 7),
        np.array([0.0003209, 0.0004209])
    )


def test_round_qty_for_live_mode():
    np.testing.assert_equal(
        jh.round_qty_for_live_mode(np.array([100.3209123456, 100.4299123456]), 2),
        np.array([100.32, 100.42])
    )

    np.testing.assert_equal(
        jh.round_qty_for_live_mode(np.array([0]), 1),
        np.array([0.1])
    )

    np.testing.assert_equal(
        jh.round_qty_for_live_mode(np.array([0]), 2),
        np.array([0.01])
    )

    np.testing.assert_equal(
        jh.round_qty_for_live_mode(np.array([0]), 3),
        np.array([0.001])
    )

    # round one number only
    to_round = 10.123456789
    expected_result = 10.1234
    res = jh.round_qty_for_live_mode(to_round, 4)
    assert res == expected_result
    assert type(res) == float


def test_round_decimals_down():
    assert jh.round_decimals_down(100.329, 2) == 100.32


def test_secure_hash():
    assert jh.secure_hash('test') == "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"


def test_should_execute_silently():
    assert jh.should_execute_silently() is True


def test_side_to_type():
    assert jh.side_to_type("buy") == "long"
    assert jh.side_to_type("sell") == "short"

    # make sure title case works as well
    assert jh.side_to_type("Buy") == "long"
    assert jh.side_to_type("Sell") == "short"


def test_string_after_character():
    assert jh.string_after_character('btcusdt@bookTicker', '@') == 'bookTicker'
    assert jh.string_after_character('9000|24628', '|') == '24628'


def test_style():
    assert jh.style('test', 'bold') == "\x1b[1mtest\x1b[0m"
    assert jh.style('test', 'u') == "\x1b[4mtest\x1b[0m"


def test_terminate_app():
    # uses database, which is not existing during testing
    pass


def test_timeframe_to_one_minutes():
    assert jh.timeframe_to_one_minutes('1m') == 1
    assert jh.timeframe_to_one_minutes('3m') == 3
    assert jh.timeframe_to_one_minutes('5m') == 5
    assert jh.timeframe_to_one_minutes('15m') == 15
    assert jh.timeframe_to_one_minutes('30m') == 30
    assert jh.timeframe_to_one_minutes('1h') == 60
    assert jh.timeframe_to_one_minutes('2h') == 60 * 2
    assert jh.timeframe_to_one_minutes('3h') == 60 * 3
    assert jh.timeframe_to_one_minutes('4h') == 60 * 4
    assert jh.timeframe_to_one_minutes('6h') == 60 * 6
    assert jh.timeframe_to_one_minutes('8h') == 60 * 8
    assert jh.timeframe_to_one_minutes('1D') == 60 * 24


def test_timestamp_to_arrow():
    arrow_time = arrow.get('2015-08-01')
    assert jh.timestamp_to_arrow(1438387200000) == arrow_time


def test_timestamp_to_date():
    assert jh.timestamp_to_date(1438387200000) == "2015-08-01"


def test_timestamp_to_time():
    assert jh.timestamp_to_time(1558770180000) == '2019-05-25T07:43:00+00:00'


def test_today_to_timestamp():
    assert jh.today_to_timestamp() == arrow.utcnow().floor('day').int_timestamp * 1000


def test_type_to_side():
    assert jh.type_to_side('long') == 'buy'
    assert jh.type_to_side('short') == 'sell'

    # validate that if sent any other string, it will raise ValueError
    with pytest.raises(ValueError):
        jh.type_to_side('invalid')


def test_unique_list():
    a = [
        ('Binance', 'BTC', '1m'),
        ('Binance', 'BTC', '5m'),
        ('Binance', 'BTC', '15m'),
        ('Binance', 'BTC', '5m'),
        ('Binance', 'BTC', '1m'),
        ('Binance', 'BTC', '15m'),
    ]

    expected = [
        ('Binance', 'BTC', '1m'),
        ('Binance', 'BTC', '5m'),
        ('Binance', 'BTC', '15m'),
    ]

    assert jh.unique_list(a) == expected


def test_closing_side():
    assert jh.closing_side('Long') == 'sell'
    assert jh.closing_side('Short') == 'buy'


def test_merge_dicts():
    client = {
        'extra': {
            'name': 'Saleh',
            'new_key': 12
        },
        'age': 28
    }

    server = {
        'extra': {
            'name': 'Ocean',
            'water': 100
        },
    }

    expected_result = {'age': 28, 'extra': {'name': 'Ocean', 'water': 100, 'new_key': 12}}

    assert expected_result == jh.merge_dicts(client, server)


def test_get_pid():
    assert os.getpid() == jh.get_pid()


def test_convert_to_env_name():
    assert jh.convert_to_env_name('Testnet Binance Futures') == 'TESTNET_BINANCE_FUTURES'
    assert jh.convert_to_env_name('Testnet Binance') == 'TESTNET_BINANCE'


def test_str_or_none():
    assert jh.str_or_none('test') == 'test'
    assert jh.str_or_none(None) is None
    assert jh.str_or_none('') is ''
    assert jh.str_or_none(3009004354) == '3009004354'
    assert jh.str_or_none(b'3009004354') == '3009004354'


def test_float_or_none():
    assert jh.float_or_none(1.23) == 1.23
    assert jh.float_or_none(1) == 1.0
    assert jh.float_or_none(None) is None
    assert jh.float_or_none('') is None
    assert jh.float_or_none(b'1.23') == 1.23
    assert jh.float_or_none('1.23') == 1.23


def test_get_class_name():
    class TestClass:
        pass

    assert jh.get_class_name(TestClass) == 'TestClass'

    # if string is passed, it will return the string
    assert jh.get_class_name('TestClass') == 'TestClass'


def test_round_or_none():
    assert jh.round_or_none(1.23) == 1
    assert jh.round_or_none(1.23456789, 2) == 1.23
    assert jh.round_or_none(None) is None
