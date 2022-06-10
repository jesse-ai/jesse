import pytest

import jesse.services.selectors as selectors
from jesse.config import config, reset_config
from jesse.enums import exchanges, timeframes, order_types
from jesse.exceptions import InvalidStrategy, NegativeBalance, OrderNotAllowed
from jesse.models import Position, Exchange
from jesse.routes import router
from jesse.services.broker import Broker
from jesse.store import store
import jesse.helpers as jh

position: Position = None
exchange: Exchange = None
broker: Broker = None


def set_up_without_fee(is_futures_trading=False):
    reset_config()
    config['env']['exchanges'][exchanges.SANDBOX]['fee'] = 0
    config['env']['exchanges'][exchanges.SANDBOX]['balance'] = 1000
    if is_futures_trading:
        # used only in futures trading
        config['env']['exchanges'][exchanges.SANDBOX]['type'] = 'futures'
    else:
        config['env']['exchanges'][exchanges.SANDBOX]['type'] = 'spot'
    config['app']['trading_mode'] = 'backtest'
    config['app']['considering_exchanges'] = ['Sandbox']
    router.initiate([
        {'exchange': exchanges.SANDBOX, 'symbol': 'BTC-USDT', 'timeframe': '5m', 'strategy': 'Test19'}
    ], [])

    global position
    global exchange
    global broker
    position = selectors.get_position(exchanges.SANDBOX, 'BTC-USDT')
    position.current_price = 50
    exchange = selectors.get_exchange(exchanges.SANDBOX)
    broker = Broker(position, exchanges.SANDBOX, 'BTC-USDT', timeframes.MINUTE_5)


def set_up_with_fee(is_futures_trading=False):
    reset_config()
    config['env']['exchanges'][exchanges.SANDBOX]['fee'] = 0.002
    config['env']['exchanges'][exchanges.SANDBOX]['balance'] = 1000
    if is_futures_trading:
        # used only in futures trading
        config['env']['exchanges'][exchanges.SANDBOX]['type'] = 'futures'
    else:
        config['env']['exchanges'][exchanges.SANDBOX]['type'] = 'spot'
    config['app']['trading_mode'] = 'backtest'
    config['app']['considering_exchanges'] = ['Sandbox']
    router.initiate([
        {'exchange': exchanges.SANDBOX, 'symbol': 'BTC-USDT', 'timeframe': '5m', 'strategy': 'Test19'}
    ], [])

    global position
    global exchange
    global broker
    position = selectors.get_position(exchanges.SANDBOX, 'BTC-USDT')
    position.current_price = 50
    exchange = selectors.get_exchange(exchanges.SANDBOX)
    broker = Broker(position, exchanges.SANDBOX, 'BTC-USDT',
                    timeframes.MINUTE_5)


def test_cancel_all_orders():
    set_up_without_fee(is_futures_trading=True)

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


def test_opening_and_closing_position_with_stop():
    set_up_without_fee(is_futures_trading=True)

    assert position.current_price == 50
    assert position.is_close is True
    assert exchange.assets['USDT'] == 1000
    assert exchange.available_margin == 1000
    assert exchange.wallet_balance == 1000
    # open position
    open_position_order = broker.start_profit_at('buy', 1, 60)
    open_position_order.execute()
    position.current_price = 60
    assert position.is_open is True
    assert position.entry_price == 60
    assert position.qty == 1
    assert exchange.assets['USDT'] == 1000
    assert exchange.wallet_balance == 1000
    assert exchange.available_margin == 940

    # submit stop-loss order
    stop_loss_order = broker.reduce_position_at(1, 40)
    assert stop_loss_order.reduce_only is True
    # balance should NOT have changed
    assert exchange.assets['USDT'] == 1000
    assert exchange.wallet_balance == 1000
    # submit take-profit order also
    take_profit_order = broker.reduce_position_at(1, 80)
    assert take_profit_order.reduce_only is True
    assert exchange.assets['USDT'] == 1000

    # execute stop order
    stop_loss_order.execute()
    position.current_price = 40
    assert exchange.assets['USDT'] == 980

    assert exchange.wallet_balance == 980
    assert exchange.available_margin == 980
    take_profit_order.cancel()
    assert exchange.available_margin == 980
    assert position.is_close is True
    assert position.entry_price is None
    assert position.exit_price == 40


def test_stop_loss():
    set_up_without_fee(is_futures_trading=True)

    assert position.current_price == 50
    assert position.is_close is True
    assert exchange.available_margin == 1000
    assert exchange.wallet_balance == 1000
    # open position
    broker.buy_at_market(1)
    # fake it
    store.orders.execute_pending_market_orders()
    assert position.is_open is True
    assert position.entry_price == 50
    assert position.qty == 1
    assert exchange.available_margin == 950
    # even executed orders should not affect wallet_balance unless it's for reducing positon
    assert exchange.wallet_balance == 1000

    order = broker.reduce_position_at(1, 40)
    assert order.type == order_types.STOP
    assert order.price == 40
    assert order.qty == -1
    assert order.side == 'sell'
    assert order.reduce_only is True
    # balance should NOT have changed
    assert exchange.available_margin == 950
    assert exchange.wallet_balance == 1000

    # execute stop order
    order.execute()
    assert position.is_close is True
    assert position.entry_price is None
    assert position.exit_price == 40
    assert exchange.available_margin == 990
    assert exchange.wallet_balance == 990


def test_should_not_submit_reduce_only_orders_when_position_is_closed():
    set_up_without_fee(is_futures_trading=True)

    with pytest.raises(OrderNotAllowed):
        broker.reduce_position_at(1, 20)

    with pytest.raises(OrderNotAllowed):
        broker.reduce_position_at(1, 20)
