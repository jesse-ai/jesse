import arrow
import pytest
import numpy as np

import jesse.helpers as jh


def test_prepare_qty():
    assert jh.prepare_qty(10, 'sell') == -10
    assert jh.prepare_qty(-10, 'buy') == 10

    with pytest.raises(TypeError):
        jh.prepare_qty(-10, 'invalid_input')


def test_estimate_average_price():
    assert jh.estimate_average_price(100, 7200, 0, 0) == 7200

    with pytest.raises(TypeError):
        jh.estimate_average_price(100, 7200, 0, None)
        jh.estimate_average_price(100, 7200, None, 0)
        jh.estimate_average_price(100, None, 0, 0)
        jh.estimate_average_price(None, 7200, 0, 0)


def test_estimate_PNL():
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


def test_estimate_profit():
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


def test_date_dif_in_days():
    date_1 = arrow.get('2015-12-23 18:40:48', 'YYYY-MM-DD HH:mm:ss')
    date_2 = arrow.get('2017-11-15 13:18:20', 'YYYY-MM-DD HH:mm:ss')
    diff = jh.date_diff_in_days(date_1, date_2)
    assert diff == 692


def test_timestamp_to_time():
    assert jh.timestamp_to_time(1558770180000) == '2019-05-25T07:43:00+00:00'


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
    assert jh.timeframe_to_one_minutes('1D') == 60 * 24


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
    assert jh.max_timeframe(['6h', '1D']) == '1D'


def test_type_to_side():
    assert jh.type_to_side('long') == 'buy'
    assert jh.type_to_side('short') == 'sell'


def test_opposite_side():
    assert jh.opposite_side('buy') == 'sell'
    assert jh.opposite_side('sell') == 'buy'


def test_opposite_type():
    assert jh.opposite_type('long') == 'short'
    assert jh.opposite_type('short') == 'long'


def test_is_unit_testing():
    assert jh.is_unit_testing() is True


def test_convert_number():
    old_max = 119
    old_min = 40
    new_max = 4.0
    new_min = 0.5
    old_value = 41

    assert jh.convert_number(old_max, old_min, new_max, new_min, old_value) == 0.5443037974683544


def test_normalize():
    assert jh.normalize(10, 0, 20) == 0.5
    assert jh.normalize(20, 0, 20) == 1
    assert jh.normalize(0, 0, 20) == 0


def test_string_after_character():
    assert jh.string_after_character('btcusdt@bookTicker', '@') == 'bookTicker'


def test_insert_list():
    my_list = [0, 1, 2, 3]

    assert jh.insert_list(2, 22, my_list) == [0, 1, 22, 2, 3]
    assert jh.insert_list(0, 22, my_list) == [22, 0, 1, 2, 3]
    assert jh.insert_list(-1, 22, my_list) == [0, 1, 2, 3, 22]

    # assert list is untouched
    assert my_list == [0, 1, 2, 3]


def test_binary_search():
    arr = [0, 11, 22, 33, 44, 54, 55]

    assert jh.binary_search(arr, 22) == 2
    assert jh.binary_search(arr, 222) == -1


def test_clean_list():
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


def test_get_config():
    # assert when config does NOT exist (must return passed default)
    assert jh.get_config('aaaaaaa', 2020) == 2020
    # assert when config does exist
    assert jh.get_config('env.logging.order_submission', 2020) is True


def test_np_shift():
    arr = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9])
    res = jh.np_shift(arr, -3)
    expected = np.array([4, 5, 6, 7, 8, 9, 0, 0, 0])

    np.equal(res, expected)


def test_date_to_timestamp():
    assert jh.date_to_timestamp('2015-08-01') == 1438387200000


def test_timestamp_to_date():
    assert jh.timestamp_to_date(1438387200000) == '2015-08-01'


def test_round_price_for_live_mode():
    np.testing.assert_equal(
        jh.round_price_for_live_mode(0.0003209123456, np.array([0.0003209123456, 0.0004209123456])),
        np.array([0.0003209, 0.0004209])
    )
    np.testing.assert_equal(
        jh.round_price_for_live_mode(0.003209123456, np.array([0.003209123456, 0.004209123456])),
        np.array([0.003209, 0.004209])
    )
    np.testing.assert_equal(
        jh.round_price_for_live_mode(0.01117123456, np.array([0.01117123456, 0.02117123456])),
        np.array([0.01117, 0.02117])
    )
    np.testing.assert_equal(
        jh.round_price_for_live_mode(0.1592123456, np.array([0.1592123456, 0.2592123456])),
        np.array([0.1592, 0.2592])
    )
    np.testing.assert_equal(
        jh.round_price_for_live_mode(2.123456, np.array([2.123456, 1.123456])),
        np.array([2.123, 1.123])
    )
    np.testing.assert_equal(
        jh.round_price_for_live_mode(137.123456, np.array([137.123456, 837.123456])),
        np.array([137.1, 837.1])
    )
    np.testing.assert_equal(
        jh.round_price_for_live_mode(6700.123456, np.array([6700.123456, 1000.123456])),
        np.array([6700, 1000])
    )


def test_round_qty_for_live_mode():
    np.testing.assert_equal(
        jh.round_qty_for_live_mode(0.0003209123456, np.array([100.0003209123456, 100.0004209123456])),
        np.array([100, 100])
    )
    np.testing.assert_equal(
        jh.round_qty_for_live_mode(0.003209123456, np.array([100.003209123456, 100.004209123456])),
        np.array([100, 100])
    )
    np.testing.assert_equal(
        jh.round_qty_for_live_mode(0.01117123456, np.array([100.01117123456, 100.02117123456])),
        np.array([100, 100])
    )
    np.testing.assert_equal(
        jh.round_qty_for_live_mode(0.1592123456, np.array([100.1592123456, 100.2592123456])),
        np.array([100, 100])
    )
    np.testing.assert_equal(
        jh.round_qty_for_live_mode(2.123456, np.array([2.123456, 1.123456])),
        np.array([2.1, 1.1])
    )
    np.testing.assert_equal(
        jh.round_qty_for_live_mode(137.123456, np.array([137.123456, 837.123456])),
        np.array([137.123, 837.123])
    )
    np.testing.assert_equal(
        jh.round_qty_for_live_mode(6700.123456, np.array([0.123456, 0.124456])),
        np.array([0.123, 0.124])
    )
