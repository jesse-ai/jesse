import jesse.services.selectors as selectors
from jesse.config import config, reset_config
from jesse.enums import exchanges, timeframes, order_types, order_flags, order_roles
from jesse.models import Position, Exchange
from jesse.routes import router
from jesse.services.broker import Broker
from jesse.store import store

position: Position = None
exchange: Exchange = None
broker: Broker = None


def set_up():
    reset_config()
    config['env']['exchanges'][exchanges.SANDBOX]['fee'] = 0
    config['env']['exchanges'][exchanges.SANDBOX]['starting_balance'] = 1000
    config['app']['trading_mode'] = 'backtest'
    config['app']['considering_exchanges'] = ['Sandbox']
    router.set_routes([(exchanges.SANDBOX, 'BTCUSD', '5m', 'Test19')])
    store.reset(True)

    global position
    global exchange
    global broker
    position = selectors.get_position(exchanges.SANDBOX, 'BTCUSD')
    position.current_price = 50
    exchange = selectors.get_exchange(exchanges.SANDBOX)
    broker = Broker(position, exchanges.SANDBOX, 'BTCUSD',
                    timeframes.MINUTE_5)


def set_up_with_fee():
    reset_config()
    config['env']['exchanges'][exchanges.SANDBOX]['fee'] = 0.002
    config['env']['exchanges'][exchanges.SANDBOX]['starting_balance'] = 1000
    config['app']['trading_mode'] = 'backtest'
    config['app']['considering_exchanges'] = ['Sandbox']
    router.set_routes([(exchanges.SANDBOX, 'BTCUSD', '5m', 'Test19')])
    store.reset(True)

    global position
    global exchange
    global broker
    position = selectors.get_position(exchanges.SANDBOX, 'BTCUSD')
    position.current_price = 50
    exchange = selectors.get_exchange(exchanges.SANDBOX)
    broker = Broker(position, exchanges.SANDBOX, 'BTCUSD',
                    timeframes.MINUTE_5)


def test_fee_calculation_when_opening_and_closing_positions():
    set_up_with_fee()

    # fee must be paid for opening the position
    assert position.qty == 0
    assert exchange.balance == 1000
    broker.sell_at_market(1)
    # fake it
    store.orders.execute_pending_market_orders()
    assert position.qty == -1
    assert exchange.balance == 949.9

    # fee must be cut again before increasing the balance when
    # closing the position
    broker.buy_at_market(1)
    # fake it
    store.orders.execute_pending_market_orders()
    assert position.is_close is True
    assert exchange.balance == 999.8


def test_fee_calculation_when_submitting_and_canceling_orders():
    set_up_with_fee()

    # fee must be cut from balance when submitting the order
    assert position.qty == 0
    assert exchange.balance == 1000
    order = broker.buy_at(2.5, 40)
    # fake it
    store.orders.execute_pending_market_orders()
    assert order.qty == 2.5
    assert order.is_active is True
    assert exchange.balance == 899.8

    # balance must be returned to the same(+fee)
    # when canceling open_position order
    order.cancel()
    assert exchange.balance == 1000

    # open a position
    broker.buy_at_market(2)
    # fake it
    store.orders.execute_pending_market_orders()
    assert exchange.balance == 899.8
    assert position.qty == 2
    # balance should be decreased when submitting increase_position order
    order = broker.buy_at(2.5, 40)
    # fake it
    store.orders.execute_pending_market_orders()
    assert round(exchange.balance, 1) == 799.6
    # balance must be returned to the same(+fee)
    # when canceling increase_position order
    order.cancel()
    assert exchange.balance == 899.8
    assert position.qty == 2

    # submitting a reduce_position should keep the balance the same
    order = broker.sell_at(2, 60)
    assert exchange.balance == 899.8
    # canceling the reduce_position order must not increase to balance
    order.cancel()
    assert exchange.balance == 899.8

    # however the balance must be incrased if the reduce_position
    # order gets executed
    assert position.qty == 2
    order = broker.sell_at(2, 60)
    assert exchange.balance == 899.8
    order.execute()
    assert position.is_close is True
    assert exchange.balance == 1019.56


def test_market_orders_and_its_effects_on_position_and_exchange():
    set_up()

    assert position.qty == 0
    assert exchange.balance == 1000

    order = broker.sell_at_market(1)
    # fake it
    store.orders.execute_pending_market_orders()
    assert position.qty == -1
    assert exchange.balance == 950
    assert order.type == order_types.MARKET

    # increase position size
    broker.sell_at_market(1)
    # fake it
    store.orders.execute_pending_market_orders()
    assert position.qty == -2
    assert exchange.balance == 900

    # reduce position size
    broker.buy_at_market(1)
    # fake it
    store.orders.execute_pending_market_orders()
    assert position.qty == -1
    assert exchange.balance == 950

    # close position
    broker.buy_at_market(1)
    # fake it
    store.orders.execute_pending_market_orders()
    assert position.qty == 0
    assert exchange.balance == 1000

    # open long position
    broker.buy_at_market(1)
    # fake it
    store.orders.execute_pending_market_orders()
    assert position.qty == 1
    assert exchange.balance == 950

    # turn it into a short position
    broker.sell_at_market(3)
    # fake it
    store.orders.execute_pending_market_orders()
    assert position.qty == -2
    assert exchange.balance == 900


def test_limit_orders():
    set_up()

    assert exchange.balance == 1000
    order = broker.buy_at(1, 40)
    assert order.price == 40
    assert order.qty == 1
    assert order.type == 'LIMIT'
    assert exchange.balance == 960
    broker.cancel_order(order.id)
    assert exchange.balance == 1000

    order = broker.sell_at(1, 60)
    assert order.price == 60
    assert order.qty == -1
    assert order.type == 'LIMIT'
    assert exchange.balance == 940
    broker.cancel_order(order.id)
    assert exchange.balance == 1000


def test_reduce_position_order():
    set_up()

    assert position.current_price == 50
    assert exchange.balance == 1000
    broker.buy_at_market(1)
    # fake it
    store.orders.execute_pending_market_orders()
    assert position.qty == 1
    assert exchange.balance == 950

    # $50 was spent at opening position
    order = broker.reduce_position_at(1, 60)
    assert order.price == 60
    assert order.qty == -1
    assert order.type == 'LIMIT'
    assert order.flag == order_flags.REDUCE_ONLY

    # neither opening nor canceling reduce position will affect balance
    assert exchange.balance == 950
    broker.cancel_order(order.id)
    assert exchange.balance == 950

    # but it's execution will
    order = broker.reduce_position_at(1, 60)
    order.execute()
    assert exchange.balance == 1010
    assert position.is_close is True


def test_start_profit():
    set_up()

    assert position.current_price == 50
    assert position.is_close is True
    assert exchange.balance == 1000

    order = broker.start_profit_at('buy', 1, 60)
    assert exchange.balance == 940
    assert order.type == order_types.STOP
    assert order.qty == 1

    order.cancel()
    assert exchange.balance == 1000

    order = broker.start_profit_at('buy', 1, 60)
    assert exchange.balance == 940
    order.execute()
    assert exchange.balance == 940
    assert position.qty == 1
    assert position.entry_price == 60


def test_stop_loss():
    set_up()

    assert position.current_price == 50
    assert position.is_close is True
    assert exchange.balance == 1000
    # open position
    broker.buy_at_market(1)
    # fake it
    store.orders.execute_pending_market_orders()
    assert position.is_open is True
    assert position.entry_price == 50
    assert position.qty == 1
    assert exchange.balance == 950

    # submit stop-loss order
    order = broker.stop_loss_at(1, 40)
    assert order.type == order_types.STOP
    assert order.price == 40
    assert order.qty == -1
    assert order.side == 'sell'
    assert order.flag == order_flags.REDUCE_ONLY
    # balance should NOT have changed
    assert exchange.balance == 950

    # execute stop order
    order.execute()
    assert position.is_close == True
    assert position.entry_price == None
    assert position.exit_price == 40
    assert exchange.balance == 990

    # make sure stop_loss order cannot open
    # position even in the other direction
    # because of its REDUCE_ONLY flag
    broker.buy_at_market(1)
    # fake it
    store.orders.execute_pending_market_orders()
    assert exchange.balance == 940
    assert position.qty == 1
    order = broker.stop_loss_at(2, 40)
    order.execute()
    assert position.qty == 0
    assert exchange.balance == 940


def test_opening_and_closing_position_with_stop():
    set_up()

    assert position.current_price == 50
    assert position.is_close is True
    assert exchange.balance == 1000
    # open position
    open_position_order = broker.start_profit_at('buy', 1, 60, order_roles.OPEN_POSITION)
    open_position_order.execute()
    assert position.is_open is True
    assert position.entry_price == 60
    assert position.qty == 1
    assert exchange.balance == 940

    # submit stop-loss order
    stop_loss_order = broker.stop_loss_at(1, 40, order_roles.CLOSE_POSITION)
    assert stop_loss_order.flag == order_flags.REDUCE_ONLY
    # balance should NOT have changed
    assert exchange.balance == 940
    # submit take-profit order also
    take_profit_order = broker.reduce_position_at(1, 80, order_roles.CLOSE_POSITION)
    assert take_profit_order.flag == order_flags.REDUCE_ONLY
    assert exchange.balance == 940

    # execute stop order
    stop_loss_order.execute()
    take_profit_order.cancel()
    assert position.is_close is True
    assert position.entry_price is None
    assert position.exit_price == 40
    assert exchange.balance == 980


def test_cancel_all_orders():
    set_up()

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
