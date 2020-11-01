import math

import numpy as np
import pytest

import jesse.helpers as jh
import jesse.services.selectors as selectors
from jesse import exceptions
from jesse.config import reset_config
from jesse.enums import exchanges, timeframes, order_roles, order_types
from jesse.factories import fake_range_candle, fake_range_candle_from_range_prices
from jesse.models import CompletedTrade
from jesse.models import Order
from jesse.modes import backtest_mode
from jesse.routes import router
from jesse.store import store
from jesse.config import config
from jesse.strategies import Strategy
from tests.data import test_candles_0
from tests.data import test_candles_1


def get_btc_and_eth_candles():
    candles = {}
    candles[jh.key(exchanges.SANDBOX, 'BTCUSDT')] = {
        'exchange': exchanges.SANDBOX,
        'symbol': 'BTCUSDT',
        'candles': fake_range_candle_from_range_prices(range(101, 200))
    }
    candles[jh.key(exchanges.SANDBOX, 'ETHUSDT')] = {
        'exchange': exchanges.SANDBOX,
        'symbol': 'ETHUSDT',
        'candles': fake_range_candle_from_range_prices(range(1, 100))
    }
    return candles


def get_btc_candles():
    candles = {}
    candles[jh.key(exchanges.SANDBOX, 'BTCUSDT')] = {
        'exchange': exchanges.SANDBOX,
        'symbol': 'BTCUSDT',
        'candles': fake_range_candle_from_range_prices(range(1, 100))
    }
    return candles


def set_up(routes, is_margin_trading=True):
    reset_config()
    config['env']['exchanges'][exchanges.SANDBOX]['assets'] = [
        {'asset': 'USDT', 'balance': 10000},
        {'asset': 'BTC', 'balance': 0},
        {'asset': 'ETH', 'balance': 0},
    ]
    if is_margin_trading:
        # used only in margin trading
        config['env']['exchanges'][exchanges.SANDBOX]['type'] = 'margin'
    else:
        config['env']['exchanges'][exchanges.SANDBOX]['type'] = 'spot'
    router.set_routes(routes)
    store.reset(True)


def single_route_backtest(strategy_name: str):
    """used to simplify simple tests"""
    set_up([(exchanges.SANDBOX, 'BTCUSDT', timeframes.MINUTE_1, strategy_name)])
    # dates are fake. just to pass required parameters
    backtest_mode.run('2019-04-01', '2019-04-02', get_btc_candles())


def test_average_stop_loss_exception():
    set_up([(exchanges.SANDBOX, 'BTCUSDT', timeframes.MINUTE_1, 'Test39')])

    with pytest.raises(exceptions.InvalidStrategy):
        backtest_mode.run('2019-04-01', '2019-04-02', get_btc_candles())


def test_average_take_profit_and_average_stop_loss():
    single_route_backtest('Test36')

    assert len(store.completed_trades.trades) == 2

    t1: CompletedTrade = store.completed_trades.trades[0]
    assert t1.type == 'long'
    assert t1.entry_price == 1
    assert t1.exit_price == 3.5
    assert t1.take_profit_at == 3.5
    assert t1.qty == 2

    t2: CompletedTrade = store.completed_trades.trades[1]
    assert t2.type == 'short'
    assert t2.entry_price == 11
    assert t2.exit_price == 13.5
    assert t2.qty == 2


def test_average_take_profit_exception():
    set_up([(exchanges.SANDBOX, 'BTCUSDT', timeframes.MINUTE_1, 'Test38')])

    with pytest.raises(exceptions.InvalidStrategy):
        backtest_mode.run('2019-04-01', '2019-04-02', get_btc_candles())


def test_can_close_a_long_position_and_go_short_at_the_same_candle():
    single_route_backtest('Test45')
    trades = store.completed_trades.trades

    assert len(trades) == 1
    assert store.app.total_open_trades == 1
    # more assertions in the Test45 file


def test_can_perform_backtest_with_multiple_routes():
    set_up([
        (exchanges.SANDBOX, 'ETHUSDT', timeframes.MINUTE_5, 'Test01'),
        (exchanges.SANDBOX, 'BTCUSDT', timeframes.MINUTE_5, 'Test02'),
    ])

    candles = {}
    routes = router.routes
    for r in routes:
        key = jh.key(r.exchange, r.symbol)
        candles[key] = {
            'exchange': r.exchange,
            'symbol': r.symbol,
            'candles': fake_range_candle((5 * 3) * 20)
        }

    # run backtest (dates are fake just to pass)
    backtest_mode.run('2019-04-01', '2019-04-02', candles)

    for r in routes:
        s: Strategy = r.strategy
        p = s.position

        assert p.is_close is True
        assert len(s.orders) == 3
        o: Order = s.orders[0]
        short_candles = store.candles.get_candles(r.exchange, r.symbol, '1m')
        assert o.price == short_candles[4][2]
        assert o.price == s.candles[0][2]
        assert o.created_at == short_candles[4][0] + 60_000
        assert o.is_executed is True
        assert s.orders[0].role == order_roles.OPEN_POSITION
        assert s.orders[0].type == order_types.MARKET
        assert s.orders[2].role == order_roles.CLOSE_POSITION
        assert s.orders[2].type == order_types.STOP
        assert s.orders[1].role == order_roles.CLOSE_POSITION
        assert s.orders[1].type == order_types.LIMIT
        assert s.trade is None
        assert len(store.completed_trades.trades) == 2
        # assert one is long and the other is a short trade
        assert (store.completed_trades.trades[0].type == 'long'
                and store.completed_trades.trades[1].type == 'short') or (
                       store.completed_trades.trades[0].type == 'short'
                       and store.completed_trades.trades[1].type == 'long')


def test_fee_rate_property():
    single_route_backtest('Test48')


def test_filter_readable_exception():
    with pytest.raises(Exception) as err:
        single_route_backtest('Test47')

    assert str(err.value).startswith("Invalid filter format")


def test_filters():
    single_route_backtest('Test37')

    assert len(store.completed_trades.trades) == 0

    # rest of the assertions have been done inside Test37


def test_forming_candles():
    reset_config()
    router.set_routes([
        (exchanges.SANDBOX, 'BTCUSDT', timeframes.MINUTE_5, 'Test19')
    ])
    router.set_extra_candles([
        (exchanges.SANDBOX, 'BTCUSDT', timeframes.MINUTE_15)
    ])
    store.reset(True)

    candles = {}
    key = jh.key(exchanges.SANDBOX, 'BTCUSDT')
    candles[key] = {
        'exchange': exchanges.SANDBOX,
        'symbol': 'BTCUSDT',
        'candles': test_candles_0
    }

    backtest_mode.run('2019-04-01', '2019-04-02', candles)

    # use math.ceil because it must include forming candle too
    assert len(store.candles.get_candles(exchanges.SANDBOX, 'BTCUSDT', timeframes.MINUTE_5)) == math.ceil(1382 / 5)
    assert len(store.candles.get_candles(exchanges.SANDBOX, 'BTCUSDT', timeframes.MINUTE_15)) == math.ceil(
        1382 / 15)


def test_increasing_position_size_after_opening():
    set_up([
        (exchanges.SANDBOX, 'BTCUSDT', timeframes.MINUTE_1, 'Test16'),
    ])

    backtest_mode.run('2019-04-01', '2019-04-02', get_btc_candles())

    assert len(store.completed_trades.trades) == 1
    t1: CompletedTrade = store.completed_trades.trades[0]
    assert t1.type == 'long'
    assert t1.entry_price == (7 + 10) / 2
    assert t1.exit_price == 15
    assert t1.take_profit_at == 15
    assert t1.stop_loss_at == 5
    assert t1.qty == 2
    assert t1.fee == 0


def test_is_increased():
    single_route_backtest('Test42')


def test_is_reduced():
    single_route_backtest('Test43')


def test_is_smart_enough_to_open_positions_via_market_orders():
    set_up([
        (exchanges.SANDBOX, 'ETHUSDT', timeframes.MINUTE_1, 'Test05'),
    ])

    candles = {}
    key = jh.key(exchanges.SANDBOX, 'ETHUSDT')
    candles[key] = {
        'exchange': exchanges.SANDBOX,
        'symbol': 'ETHUSDT',
        'candles': test_candles_1
    }

    # run backtest (dates are fake just to pass)
    backtest_mode.run('2019-04-01', '2019-04-02', candles)
    assert len(store.completed_trades.trades) == 2

    t1: CompletedTrade = store.completed_trades.trades[0]
    assert t1.type == 'long'
    assert t1.entry_price == 129.23
    assert t1.exit_price == 128.35
    assert t1.take_profit_at == 131.29
    assert t1.stop_loss_at == 128.35
    assert t1.qty == 10.204
    assert t1.fee == 0
    assert t1.opened_at == 1547201100000 + 60000
    assert t1.closed_at == 1547202840000 + 60000
    assert t1.entry_candle_timestamp == 1547201100000
    assert t1.exit_candle_timestamp == 1547202840000
    assert t1.orders[0].type == order_types.MARKET

    t2: CompletedTrade = store.completed_trades.trades[1]
    assert t2.type == 'short'
    assert t2.entry_price == 128.01
    assert t2.exit_price == 126.58
    assert t2.take_profit_at == 126.58
    assert t2.stop_loss_at == 129.52
    assert t2.qty == 10
    assert t2.fee == 0
    assert t2.opened_at == 1547203560000 + 60000
    assert t2.closed_at == 1547203740000 + 60000
    assert t2.entry_candle_timestamp == 1547203560000
    assert t2.exit_candle_timestamp == 1547203740000
    assert t2.orders[0].type == order_types.MARKET


def test_is_smart_enough_to_open_positions_via_stop_orders():
    set_up([
        (exchanges.SANDBOX, 'ETHUSDT', timeframes.MINUTE_5, 'Test06'),
    ])

    candles = {}
    key = jh.key(exchanges.SANDBOX, 'ETHUSDT')
    candles[key] = {
        'exchange': exchanges.SANDBOX,
        'symbol': 'ETHUSDT',
        'candles': test_candles_1
    }

    # run backtest (dates are fake just to pass)
    backtest_mode.run('2019-04-01', '2019-04-02', candles)
    assert len(store.completed_trades.trades) == 2

    t1: CompletedTrade = store.completed_trades.trades[0]
    assert t1.type == 'long'
    assert t1.entry_price == 129.33
    assert t1.exit_price == 128.35
    assert t1.take_profit_at == 131.29
    assert t1.stop_loss_at == 128.35
    assert t1.qty == 10.204
    assert t1.fee == 0
    assert t1.opened_at == 1547201100000 + 60000
    assert t1.closed_at == 1547202840000 + 60000
    assert t1.entry_candle_timestamp == 1547201100000
    assert t1.exit_candle_timestamp == 1547202660000
    assert t1.orders[0].type == order_types.STOP

    t2: CompletedTrade = store.completed_trades.trades[1]
    assert t2.type == 'short'
    assert t2.entry_price == 128.05
    assert t2.exit_price == 126.58
    assert t2.take_profit_at == 126.58
    assert t2.stop_loss_at == 129.52
    assert t2.qty == 10
    assert t2.fee == 0
    assert t2.opened_at == 1547203560000 + 60000
    assert t2.closed_at == 1547203740000 + 60000
    assert t2.entry_candle_timestamp == 1547203560000
    assert t2.exit_candle_timestamp == 1547203560000
    assert t2.orders[0].type == order_types.STOP


def test_liquidate():
    set_up([
        (exchanges.SANDBOX, 'BTCUSDT', timeframes.MINUTE_1, 'Test31'),
    ])

    backtest_mode.run('2019-04-01', '2019-04-02', get_btc_candles())

    assert len(store.completed_trades.trades) == 2
    t1: CompletedTrade = store.completed_trades.trades[0]
    t2: CompletedTrade = store.completed_trades.trades[1]

    assert t1.type == 'long'
    assert t1.entry_price == 1
    assert t1.exit_price == 11
    assert t1.take_profit_at == 11
    assert np.isnan(t1.stop_loss_at)

    assert t2.type == 'short'
    assert t2.entry_price == 21
    assert t2.exit_price == 41
    assert t2.stop_loss_at == 41
    assert np.isnan(t2.take_profit_at)


def test_modifying_stop_loss_after_part_of_position_is_already_reduced_with_stop_loss():
    set_up([
        (exchanges.SANDBOX, 'BTCUSDT', timeframes.MINUTE_1, 'Test14'),
    ])

    generated_candles = fake_range_candle_from_range_prices(
        list(range(1, 10)) + list(range(10, 1, -1))
    )

    candles = {}
    key = jh.key(exchanges.SANDBOX, 'BTCUSDT')
    candles[key] = {
        'exchange': exchanges.SANDBOX,
        'symbol': 'BTCUSDT',
        'candles': generated_candles
    }

    backtest_mode.run('2019-04-01', '2019-04-02', candles)

    assert len(store.completed_trades.trades) == 1
    t1: CompletedTrade = store.completed_trades.trades[0]
    assert t1.type == 'long'
    assert t1.entry_price == 7
    assert t1.exit_price == (4 * 2 + 6) / 3
    assert t1.take_profit_at == 13
    assert t1.stop_loss_at == (4 * 2 + 6) / 3
    assert t1.qty == 1.5
    assert t1.fee == 0


def test_modifying_take_profit_after_opening_position():
    set_up([
        (exchanges.SANDBOX, 'BTCUSDT', timeframes.MINUTE_5, 'Test12'),
    ])

    backtest_mode.run('2019-04-01', '2019-04-02', get_btc_candles())

    assert len(store.completed_trades.trades) == 1
    t1: CompletedTrade = store.completed_trades.trades[0]
    assert t1.type == 'long'
    assert t1.entry_price == 7
    assert t1.exit_price == 16
    assert t1.take_profit_at == 16
    assert t1.stop_loss_at == 5
    assert t1.qty == 1.5
    assert t1.fee == 0


def test_modifying_take_profit_after_part_of_position_is_already_reduced_with_profit():
    set_up([
        (exchanges.SANDBOX, 'BTCUSDT', timeframes.MINUTE_1, 'Test13'),
    ])

    backtest_mode.run('2019-04-01', '2019-04-02', get_btc_candles())

    assert len(store.completed_trades.trades) == 1
    t1: CompletedTrade = store.completed_trades.trades[0]
    assert t1.type == 'long'
    assert t1.entry_price == 7
    assert t1.exit_price == (16 * 2 + 11) / 3
    assert t1.take_profit_at == (16 * 2 + 11) / 3
    assert t1.stop_loss_at == 5
    assert t1.qty == 1.5
    assert t1.fee == 0


def test_multiple_routes_can_communicate_with_each_other():
    set_up([
        (exchanges.SANDBOX, 'ETHUSDT', timeframes.MINUTE_5, 'Test03'),
        (exchanges.SANDBOX, 'BTCUSDT', timeframes.MINUTE_5, 'Test03'),
    ])

    candles = {}
    routes = router.routes
    for r in routes:
        key = jh.key(r.exchange, r.symbol)
        candles[key] = {
            'exchange': r.exchange,
            'symbol': r.symbol,
            'candles': fake_range_candle((5 * 3) * 20)
        }

    # run backtest (dates are fake just to pass)
    backtest_mode.run('2019-04-01', '2019-04-02', candles)

    assert len(store.completed_trades.trades) == 1

    for r in routes:
        s: Strategy = r.strategy
        p = s.position

        assert p.is_close is True
        o: Order = s.orders[0]
        short_candles = store.candles.get_candles(r.exchange, r.symbol, '1m')
        assert o.created_at == short_candles[4][0] + 60_000
        if r.strategy.trades_count == 1:
            assert len(s.orders) == 3
            assert o.is_executed is True
            assert s.orders[0].role == order_roles.OPEN_POSITION
            assert s.orders[0].type == order_types.LIMIT
            assert s.orders[2].role == order_roles.CLOSE_POSITION
            assert s.orders[2].type == order_types.STOP
            assert s.orders[1].role == order_roles.CLOSE_POSITION
            assert s.orders[1].type == order_types.LIMIT
        elif r.strategy.trades_count == 0:
            assert len(s.orders) == 1
            # assert that the order got canceled
            assert o.is_canceled is True
            assert s.orders[0].role == order_roles.OPEN_POSITION
            assert s.orders[0].type == order_types.LIMIT


def test_must_not_be_able_to_set_two_similar_routes():
    reset_config()
    router.set_routes([
        (exchanges.SANDBOX, 'ETHUSDT', timeframes.MINUTE_5, 'Test01'),
        (exchanges.SANDBOX, 'ETHUSDT', timeframes.MINUTE_30, 'Test02'),
    ])
    with pytest.raises(Exception) as err:
        store.reset(True)
    assert str(
        err.value).startswith('each exchange-symbol pair can be traded only once')


def test_on_reduced_position():
    set_up([
        (exchanges.SANDBOX, 'BTCUSDT', timeframes.MINUTE_1, 'Test18'),
    ])

    backtest_mode.run('2019-04-01', '2019-04-02', get_btc_candles())

    assert len(store.completed_trades.trades) == 1
    t1: CompletedTrade = store.completed_trades.trades[0]
    assert t1.type == 'long'
    assert t1.entry_price == 7
    assert t1.exit_price == 13
    assert t1.take_profit_at == 13
    assert t1.stop_loss_at == 5
    assert t1.qty == 2
    assert t1.fee == 0


def test_on_route_canceled():
    set_up([
        (exchanges.SANDBOX, 'BTCUSDT', timeframes.MINUTE_1, 'Test27'),
        (exchanges.SANDBOX, 'ETHUSDT', timeframes.MINUTE_1, 'Test28'),
    ])

    backtest_mode.run('2019-04-01', '2019-04-02', get_btc_and_eth_candles())

    t1 = store.completed_trades.trades[0]

    assert t1.symbol == 'BTCUSDT'
    assert t1.type == 'long'
    assert t1.entry_price == 101
    assert t1.exit_price == 120
    assert t1.take_profit_at == 120
    assert t1.qty == 1
    assert np.isnan(t1.stop_loss_at)


def test_on_route_increased_position_and_on_route_reduced_position_and_strategy_vars():
    set_up([
        (exchanges.SANDBOX, 'BTCUSDT', timeframes.MINUTE_1, 'Test29'),
        (exchanges.SANDBOX, 'ETHUSDT', timeframes.MINUTE_1, 'Test30'),
    ])

    backtest_mode.run('2019-04-01', '2019-04-02', get_btc_and_eth_candles())

    # long BTCUSD
    t1 = store.completed_trades.trades[0]
    # short BTCUSD
    t2 = store.completed_trades.trades[1]
    # long ETHUSD
    t3 = store.completed_trades.trades[2]

    assert t1.symbol == 'BTCUSDT'
    assert t1.type == 'long'
    assert t1.entry_price == 121
    assert t1.exit_price == 131
    assert t1.take_profit_at == 131
    assert t1.qty == 1
    assert np.isnan(t1.stop_loss_at)

    assert t2.symbol == 'BTCUSDT'
    assert t2.type == 'short'
    assert t2.entry_price == 151
    assert t2.exit_price == 161
    assert t2.stop_loss_at == 161
    assert t2.qty == 1
    assert np.isnan(t2.take_profit_at)

    assert t3.symbol == 'ETHUSDT'
    assert t3.type == 'long'
    # because we open at 10, and increase at 20, entry is the mean which is 15
    assert t3.entry_price == 15
    # (50 + 70) / 2
    assert t3.exit_price == 60
    assert t3.take_profit_at == 60
    assert t3.qty == 2
    assert np.isnan(t3.stop_loss_at)


def test_on_route_open_position():
    set_up([
        (exchanges.SANDBOX, 'BTCUSDT', timeframes.MINUTE_1, 'Test21'),
        (exchanges.SANDBOX, 'ETHUSDT', timeframes.MINUTE_1, 'Test22'),
    ])

    backtest_mode.run('2019-04-01', '2019-04-02', get_btc_and_eth_candles())

    t1 = store.completed_trades.trades[0]
    t2 = store.completed_trades.trades[1]

    assert t1.symbol == 'BTCUSDT'
    assert t1.type == 'long'
    assert t1.entry_price == 101
    assert t1.exit_price == 110
    assert t1.take_profit_at == 110
    assert t1.qty == 1
    assert np.isnan(t1.stop_loss_at)

    assert t2.symbol == 'ETHUSDT'
    assert t2.type == 'long'
    assert t2.entry_price == 10
    assert t2.exit_price == 20
    assert t2.take_profit_at == 20
    assert t2.qty == 1
    assert np.isnan(t2.stop_loss_at)


def test_on_route_stop_loss():
    set_up([
        (exchanges.SANDBOX, 'BTCUSDT', timeframes.MINUTE_1, 'Test25'),
        (exchanges.SANDBOX, 'ETHUSDT', timeframes.MINUTE_1, 'Test26'),
    ])

    backtest_mode.run('2019-04-01', '2019-04-02', get_btc_and_eth_candles())

    t1 = store.completed_trades.trades[0]
    t2 = store.completed_trades.trades[1]

    assert t2.symbol == 'BTCUSDT'
    assert t2.type == 'long'
    assert t2.entry_price == 101
    assert t2.exit_price == 120
    assert t2.take_profit_at == 120
    assert t2.qty == 1
    assert np.isnan(t2.stop_loss_at)

    assert t1.symbol == 'ETHUSDT'
    assert t1.type == 'short'
    assert t1.entry_price == 10
    assert t1.exit_price == 20
    assert t1.stop_loss_at == 20
    assert t1.qty == 1
    assert np.isnan(t1.take_profit_at)


def test_on_route_take_profit():
    set_up([
        (exchanges.SANDBOX, 'BTCUSDT', timeframes.MINUTE_1, 'Test23'),
        (exchanges.SANDBOX, 'ETHUSDT', timeframes.MINUTE_1, 'Test24'),
    ])

    backtest_mode.run('2019-04-01', '2019-04-02', get_btc_and_eth_candles())

    t1 = store.completed_trades.trades[0]
    t2 = store.completed_trades.trades[1]

    assert t2.symbol == 'BTCUSDT'
    assert t2.type == 'long'
    assert t2.entry_price == 101
    assert t2.exit_price == 120
    assert t2.take_profit_at == 120
    assert t2.qty == 1
    assert np.isnan(t2.stop_loss_at)

    assert t1.symbol == 'ETHUSDT'
    assert t1.type == 'long'
    assert t1.entry_price == 10
    assert t1.exit_price == 20
    assert t1.take_profit_at == 20
    assert t1.qty == 1
    assert np.isnan(t1.stop_loss_at)


def test_opening_position_in_multiple_points():
    set_up([
        (exchanges.SANDBOX, 'BTCUSDT', timeframes.MINUTE_1, 'Test15'),
    ])

    backtest_mode.run('2019-04-01', '2019-04-02', get_btc_candles())

    assert len(store.completed_trades.trades) == 1
    t1: CompletedTrade = store.completed_trades.trades[0]
    assert t1.type == 'long'
    assert t1.entry_price == (7 + 9 + 11) / 3
    assert t1.exit_price == 15
    assert t1.take_profit_at == 15
    assert t1.stop_loss_at == 5
    assert t1.qty == 1.5
    assert t1.fee == 0


def test_reducing_position_size_after_opening():
    set_up([
        (exchanges.SANDBOX, 'BTCUSDT', timeframes.MINUTE_1, 'Test17'),
    ])

    backtest_mode.run('2019-04-01', '2019-04-02', get_btc_candles())

    assert len(store.completed_trades.trades) == 1
    t1: CompletedTrade = store.completed_trades.trades[0]
    assert t1.type == 'long'
    assert t1.entry_price == 7
    assert t1.exit_price == (15 + 10) / 2
    assert t1.take_profit_at == (15 + 10) / 2
    assert t1.stop_loss_at == 5
    assert t1.qty == 2
    assert t1.fee == 0


def test_shared_vars():
    set_up([
        (exchanges.SANDBOX, 'BTCUSDT', timeframes.MINUTE_1, 'Test32'),
        (exchanges.SANDBOX, 'ETHUSDT', timeframes.MINUTE_1, 'Test33'),
    ])

    backtest_mode.run('2019-04-01', '2019-04-02', get_btc_and_eth_candles())

    t1 = store.completed_trades.trades[0]

    assert t1.symbol == 'ETHUSDT'
    assert t1.type == 'long'
    assert t1.entry_price == 11
    assert t1.exit_price == 21
    assert t1.take_profit_at == 21
    assert t1.qty == 1
    assert np.isnan(t1.stop_loss_at)


def test_should_buy_and_execute_buy():
    set_up([
        (exchanges.SANDBOX, 'ETHUSDT', timeframes.MINUTE_5, 'Test01'),
    ])

    candles = {}
    routes = router.routes
    for r in routes:
        key = jh.key(r.exchange, r.symbol)
        candles[key] = {
            'exchange': r.exchange,
            'symbol': r.symbol,
            'candles': fake_range_candle((5 * 3) * 20)
        }

    # run backtest (dates are fake just to pass)
    backtest_mode.run('2019-04-01', '2019-04-02', candles)

    for r in routes:
        s: Strategy = r.strategy
        p = s.position

        assert p.is_close is True
        assert len(s.orders) == 3
        o: Order = s.orders[0]
        short_candles = store.candles.get_candles(r.exchange, r.symbol, '1m')
        assert o.price == short_candles[4][2]
        assert o.price == s.candles[0][2]
        assert o.created_at == short_candles[4][0] + 60_000
        assert o.is_executed is True
        assert s.orders[1].role == order_roles.CLOSE_POSITION
        assert s.orders[2].role == order_roles.CLOSE_POSITION
        assert s.orders[0].role == order_roles.OPEN_POSITION
        assert s.trade is None
        trade: CompletedTrade = store.completed_trades.trades[0]
        assert trade.type == 'long'
        # must include executed orders, in this case it's entry and take_profit
        assert len(trade.orders) == 2
        assert trade.orders[0].side == 'buy'
        assert trade.orders[0].type == 'MARKET'
        assert trade.orders[1].side == 'sell'
        assert trade.orders[1].type == 'LIMIT'
        assert len(store.completed_trades.trades) == 1


def test_should_sell_and_execute_sell():
    set_up([
        (exchanges.SANDBOX, 'ETHUSDT', timeframes.MINUTE_5, 'Test02'),
    ])

    candles = {}
    routes = router.routes
    for r in routes:
        key = jh.key(r.exchange, r.symbol)
        candles[key] = {
            'exchange': r.exchange,
            'symbol': r.symbol,
            'candles': fake_range_candle((5 * 3) * 20)
        }

    # run backtest (dates are fake just to pass)
    backtest_mode.run('2019-04-01', '2019-04-02', candles)

    for r in routes:
        s: Strategy = r.strategy
        p = s.position

        assert p.is_close is True
        assert len(s.orders) == 3
        o: Order = s.orders[0]
        short_candles = store.candles.get_candles(r.exchange, r.symbol, '1m')
        assert o.price == short_candles[4][2]
        assert o.price == s.candles[0][2]
        assert o.created_at == short_candles[4][0] + 60_000
        assert o.is_executed is True
        assert s.orders[1].role == order_roles.CLOSE_POSITION
        assert s.orders[2].role == order_roles.CLOSE_POSITION
        assert s.orders[0].role == order_roles.OPEN_POSITION
        assert s.trade is None
        assert len(store.completed_trades.trades) == 1
        assert store.completed_trades.trades[0].type == 'short'


def test_stop_loss_at_multiple_points():
    set_up([
        (exchanges.SANDBOX, 'BTCUSDT', timeframes.MINUTE_1, 'Test11'),
    ])

    backtest_mode.run('2019-04-01', '2019-04-02', get_btc_candles())

    assert len(store.completed_trades.trades) == 1
    t1: CompletedTrade = store.completed_trades.trades[0]
    assert t1.type == 'short'
    assert t1.entry_price == 3
    assert t1.exit_price == (6 + 5 + 4) / 3
    assert t1.take_profit_at == 1
    assert t1.stop_loss_at == (6 + 5 + 4) / 3
    assert t1.qty == 1.5
    assert t1.fee == 0


def test_strategy_properties():
    set_up([
        (exchanges.SANDBOX, 'ETHUSDT', timeframes.MINUTE_5, 'Test19'),
        (exchanges.SANDBOX, 'BTCUSDT', timeframes.MINUTE_5, 'Test19'),
    ])

    candles = {}
    routes = router.routes
    for r in routes:
        key = jh.key(r.exchange, r.symbol)
        candles[key] = {
            'exchange': r.exchange,
            'symbol': r.symbol,
            'candles': fake_range_candle((5 * 3) * 20)
        }

    # run backtest (dates are fake just to pass)
    backtest_mode.run('2019-04-01', '2019-04-02', candles)

    for r in routes:
        s: Strategy = r.strategy

        assert s.name == r.strategy_name
        assert s.symbol == r.symbol
        assert s.exchange == r.exchange
        assert s.timeframe == r.timeframe
        assert s.trade is None
        assert s._is_executing is False
        assert s._is_initiated is True
        np.testing.assert_equal(s.current_candle, store.candles.get_current_candle(r.exchange, r.symbol, r.timeframe))
        np.testing.assert_equal(s.candles, store.candles.get_candles(r.exchange, r.symbol, r.timeframe))
        assert s.position == selectors.get_position(r.exchange, r.symbol)
        assert s.orders == store.orders.get_orders(r.exchange, r.symbol)


def test_taking_profit_at_multiple_points():
    set_up([
        (exchanges.SANDBOX, 'BTCUSDT', timeframes.MINUTE_5, 'Test10'),
    ])

    backtest_mode.run('2019-04-01', '2019-04-02', get_btc_candles())

    assert len(store.completed_trades.trades) == 1
    t1: CompletedTrade = store.completed_trades.trades[0]
    assert t1.type == 'long'
    assert t1.entry_price == 7
    assert t1.exit_price == (15 + 13 + 11) / 3
    assert t1.take_profit_at == (15 + 13 + 11) / 3
    assert t1.stop_loss_at == 5
    assert t1.qty == 1.5
    assert t1.fee == 0
    assert t1.holding_period == 8 * 60


def test_terminate():
    """
    test that user can use terminate() method. in this unit test use it
    to close the open position.
    """
    single_route_backtest('Test41')

    # assert terminate() is actually executed by logging a
    # string init, and then checking for that log message
    assert {'message': 'executed terminate successfully', 'time': 1552315246171.0} in store.logs.info

    # assert inside strategies terminate() that we have indeed an open position

    # assert that Strategies's terminate() method closes the open position
    assert store.app.total_open_trades == 0
    assert store.app.total_open_pl == 0


def test_terminate_closes_trades_at_the_end_of_backtest():
    single_route_backtest('Test40')

    # assert that Strategies's _terminate() method closes the open position
    assert store.app.total_open_trades == 1
    assert store.app.total_open_pl == 97

    assert {
               'time': 1552315246171.0,
               'message': 'Closed open Sandbox-BTCUSDT position at 99.0 with PNL: 97.0(4850.0%) because we reached the end of the backtest session.'
           } in store.logs.info


def test_updating_stop_loss_and_take_profit_after_opening_the_position():
    set_up([
        (exchanges.SANDBOX, 'ETHUSDT', timeframes.MINUTE_1, 'Test07')
    ])

    candles = {}
    key = jh.key(exchanges.SANDBOX, 'ETHUSDT')
    candles[key] = {
        'exchange': exchanges.SANDBOX,
        'symbol': 'ETHUSDT',
        'candles': test_candles_1
    }

    # run backtest (dates are fake just to pass)
    backtest_mode.run('2019-04-01', '2019-04-02', candles)

    t1: CompletedTrade = store.completed_trades.trades[0]
    assert t1.type == 'long'
    assert t1.entry_price == 129.23
    assert t1.exit_price == 128.98
    assert t1.take_profit_at == 131.29
    assert t1.stop_loss_at == 128.98
    assert t1.qty == 10.204
    assert t1.fee == 0
    assert t1.opened_at == 1547201100000 + 60000
    assert t1.closed_at == 1547201700000 + 60000
    assert t1.entry_candle_timestamp == 1547201100000
    assert t1.exit_candle_timestamp == 1547201700000
    assert t1.orders[0].type == order_types.MARKET

    t2: CompletedTrade = store.completed_trades.trades[1]
    assert t2.type == 'short'
    assert t2.entry_price == 128.01
    assert t2.exit_price == 127.66
    assert t2.take_profit_at == 127.66
    assert t2.stop_loss_at == 129.52
    assert t2.qty == 10
    assert t2.fee == 0
    assert t2.opened_at == 1547203560000 + 60000
    assert t2.closed_at == 1547203680000 + 60000
    assert t2.entry_candle_timestamp == 1547203560000
    assert t2.exit_candle_timestamp == 1547203680000
    assert t2.orders[0].type == order_types.MARKET


def test_validation_for_equal_stop_loss_and_take_profit():
    with pytest.raises(Exception) as err:
        single_route_backtest('Test46')

    assert str(err.value).startswith('stop-loss and take-profit should not be exactly the same')

# def test_inputs_get_rounded_behind_the_scene():
#     set_up([(exchanges.SANDBOX, 'EOSUSDT', timeframes.MINUTE_1, 'Test44')])
#     candles = {}
#     candles[jh.key(exchanges.SANDBOX, 'EOSUSDT')] = {
#         'exchange': exchanges.SANDBOX,
#         'symbol': 'EOSUSDT',
#         'candles': fake_range_candle_from_range_prices(range(1, 100))
#     }
#     backtest_mode.run('2019-04-01', '2019-04-02', candles)
#
#     t: CompletedTrade = store.completed_trades.trades[0]
#
#     assert len(store.completed_trades.trades) == 1
#     assert t.qty == 1.5
#     assert t.entry_price == 5.123
#     assert t.take_profit_at == 10.12
#     assert t.stop_loss_at == 1.123
