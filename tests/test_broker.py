import pytest

import jesse.services.selectors as selectors
from jesse.config import config, reset_config
from jesse.enums import exchanges, timeframes, order_types, order_flags, order_roles
from jesse.exceptions import InvalidStrategy, NegativeBalance, OrderNotAllowed
from jesse.models import Position, Exchange
from jesse.routes import router
from jesse.services.broker import Broker
from jesse.store import store

position: Position = None
exchange: Exchange = None
broker: Broker = None


def set_up_without_fee(is_margin_trading=False):
    reset_config()
    config['env']['exchanges'][exchanges.SANDBOX]['fee'] = 0
    config['env']['exchanges'][exchanges.SANDBOX]['assets'] = [
        {'asset': 'USDT', 'balance': 1000},
        {'asset': 'BTC', 'balance': 0},
    ]
    if is_margin_trading:
        # used only in margin trading
        config['env']['exchanges'][exchanges.SANDBOX]['type'] = 'margin'
    else:
        config['env']['exchanges'][exchanges.SANDBOX]['type'] = 'spot'
    config['env']['exchanges'][exchanges.SANDBOX]['settlement_currency'] = 'USDT'
    config['app']['trading_mode'] = 'backtest'
    config['app']['considering_exchanges'] = ['Sandbox']
    router.set_routes([(exchanges.SANDBOX, 'BTCUSDT', '5m', 'Test19')])
    store.reset(True)

    global position
    global exchange
    global broker
    position = selectors.get_position(exchanges.SANDBOX, 'BTCUSDT')
    position.current_price = 50
    exchange = selectors.get_exchange(exchanges.SANDBOX)
    broker = Broker(position, exchanges.SANDBOX, 'BTCUSDT', timeframes.MINUTE_5)


def set_up_with_fee(is_margin_trading=False):
    reset_config()
    config['env']['exchanges'][exchanges.SANDBOX]['fee'] = 0.002
    config['env']['exchanges'][exchanges.SANDBOX]['assets'] = [
        {'asset': 'USDT', 'balance': 1000},
        {'asset': 'BTC', 'balance': 0},
    ]
    if is_margin_trading:
        # used only in margin trading
        config['env']['exchanges'][exchanges.SANDBOX]['type'] = 'margin'
    else:
        config['env']['exchanges'][exchanges.SANDBOX]['type'] = 'spot'
    config['env']['exchanges'][exchanges.SANDBOX]['settlement_currency'] = 'USDT'
    config['app']['trading_mode'] = 'backtest'
    config['app']['considering_exchanges'] = ['Sandbox']
    router.set_routes([(exchanges.SANDBOX, 'BTCUSDT', '5m', 'Test19')])
    store.reset(True)

    global position
    global exchange
    global broker
    position = selectors.get_position(exchanges.SANDBOX, 'BTCUSDT')
    position.current_price = 50
    exchange = selectors.get_exchange(exchanges.SANDBOX)
    broker = Broker(position, exchanges.SANDBOX, 'BTCUSDT',
                    timeframes.MINUTE_5)


def test_cancel_all_orders():
    set_up_without_fee()

    # create 3 ACTIVE orders
    o1 = broker.buy_at(1, 40)
    o2 = broker.buy_at(1, 41)
    o3 = broker.buy_at(1, 42)
    assert o1.is_active
    assert o2.is_active
    assert o3.is_active

    # create 2 EXECUTED orders
    o4 = broker.buy_at_market(1)
    # fake it
    store.orders.execute_pending_market_orders()
    o5 = broker.buy_at_market(2)
    # fake it
    store.orders.execute_pending_market_orders()
    assert o4.is_executed
    assert o5.is_executed

    broker.cancel_all_orders()

    # ACTIVE orders should have been canceled
    assert o1.is_active is False
    assert o2.is_active is False
    assert o3.is_active is False
    assert o1.is_canceled is True
    assert o2.is_canceled is True
    assert o3.is_canceled is True
    # already-executed orders should have remain the same
    assert o4.is_executed
    assert o5.is_executed
    assert o4.is_canceled is False
    assert o5.is_canceled is False


def test_limit_orders():
    set_up_with_fee()

    assert exchange.assets['USDT'] == 1000
    assert exchange.available_assets['USDT'] == 1000
    order = broker.buy_at(1, 40)
    assert order.price == 40
    assert order.qty == 1
    assert order.type == 'LIMIT'
    assert exchange.available_assets['USDT'] == 959.92
    assert exchange.assets['USDT'] == 1000
    broker.cancel_order(order.id)
    assert exchange.assets['USDT'] == 1000
    assert exchange.available_assets['USDT'] == 1000

    # buy again, this time execute
    order = broker.buy_at(1, 40)
    assert exchange.available_assets['USDT'] == 959.92
    order.execute()
    assert exchange.assets['BTC'] == 1
    assert exchange.available_assets['BTC'] == 1

    assert exchange.assets['USDT'] == 959.92
    order = broker.sell_at(1, 60)
    assert order.price == 60
    assert order.qty == -1
    assert order.type == 'LIMIT'
    assert exchange.assets['USDT'] == 959.92
    assert exchange.available_assets['BTC'] == 0
    assert exchange.assets['BTC'] == 1
    broker.cancel_order(order.id)
    assert exchange.assets['BTC'] == 1
    assert exchange.assets['USDT'] == 959.92
    assert exchange.available_assets['USDT'] == 959.92

    order = broker.sell_at(1, 60)
    order.execute()
    assert exchange.assets['BTC'] == 0
    assert exchange.available_assets['BTC'] == 0
    assert exchange.assets['USDT'] == 1019.8
    assert exchange.available_assets['USDT'] == 1019.8

    # validate that when qty for base asset is 0 (spot market)
    with pytest.raises(NegativeBalance):
        broker.sell_at(1, 60)

    # validation: qty cannot be 0
    with pytest.raises(InvalidStrategy):
        broker.sell_at(0, 100)
        broker.buy_at(0, 100)


def test_opening_and_closing_position_with_stop():
    set_up_without_fee(is_margin_trading=True)

    assert position.current_price == 50
    assert position.is_close is True
    assert exchange.assets['USDT'] == 1000
    assert exchange.tradable_balance() == 1000
    # open position
    open_position_order = broker.start_profit_at('buy', 1, 60, order_roles.OPEN_POSITION)
    open_position_order.execute()
    assert position.is_open is True
    assert position.entry_price == 60
    assert position.qty == 1
    assert exchange.assets['USDT'] == 1000
    assert exchange.tradable_balance() == 940

    # submit stop-loss order
    stop_loss_order = broker.stop_loss_at(1, 40, order_roles.CLOSE_POSITION)
    assert stop_loss_order.flag == order_flags.REDUCE_ONLY
    # balance should NOT have changed
    assert exchange.assets['USDT'] == 1000
    # submit take-profit order also
    take_profit_order = broker.reduce_position_at(1, 80, order_roles.CLOSE_POSITION)
    assert take_profit_order.flag == order_flags.REDUCE_ONLY
    assert exchange.assets['USDT'] == 1000

    # execute stop order
    stop_loss_order.execute()
    assert exchange.assets['USDT'] == 980
    assert exchange.tradable_balance() == 900
    take_profit_order.cancel()
    assert exchange.tradable_balance() == 900 + 80
    assert position.is_close is True
    assert position.entry_price is None
    assert position.exit_price == 40


def test_start_profit():
    set_up_without_fee()

    assert position.current_price == 50
    assert position.is_close is True
    assert exchange.assets['USDT'] == 1000
    assert exchange.available_assets['USDT'] == 1000

    order = broker.start_profit_at('buy', 1, 60)
    assert exchange.available_assets['USDT'] == 940
    assert exchange.assets['USDT'] == 1000
    assert order.type == order_types.STOP
    assert order.qty == 1

    order.cancel()
    assert exchange.assets['USDT'] == 1000
    assert exchange.available_assets['USDT'] == 1000

    order = broker.start_profit_at('buy', 1, 60)
    assert exchange.available_assets['USDT'] == 940
    assert exchange.assets['USDT'] == 1000
    order.execute()
    assert exchange.assets['USDT'] == 940
    assert exchange.available_assets['USDT'] == 940
    assert position.qty == 1
    assert position.entry_price == 60

    # validation: qty cannot be 0
    with pytest.raises(InvalidStrategy):
        broker.start_profit_at('buy', 0, 100)


def test_stop_loss():
    set_up_without_fee(is_margin_trading=True)

    assert position.current_price == 50
    assert position.is_close is True
    assert exchange.tradable_balance() == 1000
    # open position
    broker.buy_at_market(1)
    # fake it
    store.orders.execute_pending_market_orders()
    assert position.is_open is True
    assert position.entry_price == 50
    assert position.qty == 1
    assert exchange.tradable_balance() == 950

    order = broker.stop_loss_at(1, 40)
    assert order.type == order_types.STOP
    assert order.price == 40
    assert order.qty == -1
    assert order.side == 'sell'
    assert order.flag == order_flags.REDUCE_ONLY
    # balance should NOT have changed
    assert exchange.tradable_balance() == 950

    # execute stop order
    order.execute()
    assert position.is_close is True
    assert position.entry_price is None
    assert position.exit_price == 40
    assert exchange.tradable_balance() == 990


def test_should_not_submit_reduce_only_orders_when_position_is_closed():
    set_up_without_fee(is_margin_trading=True)

    with pytest.raises(OrderNotAllowed):
        broker.reduce_position_at(1, 20)

    with pytest.raises(OrderNotAllowed):
        broker.stop_loss_at(1, 20)
