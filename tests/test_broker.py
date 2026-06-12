import pytest
from jesse.config import config, reset_config
from jesse.enums import exchanges, timeframes, order_types
from jesse.exceptions import OrderNotAllowed
from jesse.models import Position, Exchange
from jesse.routes import router
from jesse.services.broker import Broker
from jesse.services import order_service, exchange_service, position_service
from jesse.store import store


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
    # reset store
    store.reset() 
    # initialize exchanges state
    exchange_service.initialize_exchanges_state()
    # initialize orders state
    order_service.initialize_orders_state()
    # initialize positions state
    position_service.initialize_positions_state()

    global position
    global exchange
    global broker
    position = store.positions.get_position(exchanges.SANDBOX, 'BTC-USDT')
    position.current_price = 50
    exchange = store.exchanges.get_exchange(exchanges.SANDBOX)
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
    # reset store
    store.reset() 
    # initialize exchanges state
    exchange_service.initialize_exchanges_state()
    # initialize orders state
    order_service.initialize_orders_state()
    # initialize positions state
    position_service.initialize_positions_state()

    global position
    global exchange
    global broker
    position = store.positions.get_position(exchanges.SANDBOX, 'BTC-USDT')
    position.current_price = 50
    exchange = store.exchanges.get_exchange(exchanges.SANDBOX)
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
    for o in store.orders.to_execute:
        order_service.execute_order(o)
    store.orders.to_execute = []
    o5 = broker.buy_at_market(2)
    # fake it
    for o in store.orders.to_execute:
        order_service.execute_order(o)
    store.orders.to_execute = []
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
    order_service.execute_order(open_position_order)
    position.current_price = 60
    assert position.is_open is True
    assert position.entry_price == 60
    assert position.qty == 1
    assert exchange.assets['USDT'] == 1000
    assert exchange.wallet_balance == 1000
    assert exchange.available_margin == 940

    # submit stop-loss order
    stop_loss_order = broker.reduce_position_at(1, 40, 60)
    assert stop_loss_order.reduce_only is True
    # balance should NOT have changed
    assert exchange.assets['USDT'] == 1000
    assert exchange.wallet_balance == 1000
    # submit take-profit order also
    take_profit_order = broker.reduce_position_at(1, 80, 60)
    assert take_profit_order.reduce_only is True
    assert exchange.assets['USDT'] == 1000

    # execute stop order
    order_service.execute_order(stop_loss_order)
    position.current_price = 40
    assert exchange.assets['USDT'] == 980

    assert exchange.wallet_balance == 980
    assert exchange.available_margin == 980
    order_service.cancel_order(take_profit_order)
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
    for o in store.orders.to_execute:
        order_service.execute_order(o)
    store.orders.to_execute = []
    assert position.is_open is True
    assert position.entry_price == 50
    assert position.qty == 1
    assert exchange.available_margin == 950
    # even executed orders should not affect wallet_balance unless it's for reducing position
    assert exchange.wallet_balance == 1000

    order = broker.reduce_position_at(1, 40, 50)
    assert order.type == order_types.STOP
    assert order.price == 40
    assert order.qty == -1
    assert order.side == 'sell'
    assert order.reduce_only is True
    # balance should NOT have changed
    assert exchange.available_margin == 950
    assert exchange.wallet_balance == 1000

    # execute stop order
    order_service.execute_order(order)
    assert position.is_close is True
    assert position.entry_price is None
    assert position.exit_price == 40
    assert exchange.available_margin == 990
    assert exchange.wallet_balance == 990


def test_should_not_submit_reduce_only_orders_when_position_is_closed():
    set_up_without_fee(is_futures_trading=True)

    with pytest.raises(OrderNotAllowed):
        broker.reduce_position_at(1, 20, 20)

    with pytest.raises(OrderNotAllowed):
        broker.reduce_position_at(1, 20, 20)


def test_oversized_reduce_only_order_uses_actual_filled_qty():
    """
    Regression: when a reduce_only stop-loss is left with a stated qty larger than the
    remaining position (e.g. a stop-loss not resized after a partial take-profit), the
    engine caps the actual fill via reduce_only. The trade's exit_price VWAP and fee must
    use that capped (actual) qty, not the stated qty — otherwise net_profit drifts below
    the real wallet balance change.
    """
    set_up_with_fee(is_futures_trading=True)

    starting_balance = exchange.wallet_balance
    assert starting_balance == 1000

    # open a long position of qty 1 @ 50
    broker.buy_at_market(1)
    for o in store.orders.to_execute:
        order_service.execute_order(o)
    store.orders.to_execute = []
    assert position.qty == 1
    assert position.entry_price == 50

    # take partial profit: sell 0.7 @ 80 (limit), position -> 0.3
    position.current_price = 50
    tp_order = broker.reduce_position_at(0.7, 80, 50)
    order_service.execute_order(tp_order)
    position.current_price = 80
    assert round(position.qty, 8) == 0.3

    # submit an OVERSIZED stop-loss: stated qty 1 (full) while only 0.3 remains, @ 40
    sl_order = broker.reduce_position_at(1, 40, 80)
    assert sl_order.reduce_only is True
    assert sl_order.qty == -1  # stated qty is oversized vs the remaining 0.3

    # execute the stop -> reduce_only caps the actual fill to the remaining 0.3
    order_service.execute_order(sl_order)
    position.current_price = 40
    assert position.is_close is True

    # the actual fill is capped to the remaining position, not the stated qty
    assert round(sl_order.filled_qty, 8) == -0.3

    trade = store.closed_trades.trades[-1]

    # exit_price VWAP must weight the SL leg by the ACTUAL 0.3, not the stated 1.0:
    # (0.7*80 + 0.3*40) / (0.7+0.3) = 68, NOT (0.7*80 + 1.0*40) / 1.7 = 56.47
    assert round(trade.exit_price, 8) == 68

    # fee must be charged on the actual filled qty across all legs
    expected_fee = (1 * 50 + 0.7 * 80 + 0.3 * 40) * 0.002
    assert round(trade.fee, 8) == round(expected_fee, 8)

    # headline check: per-trade net profit equals the real wallet balance change
    wallet_delta = exchange.wallet_balance - starting_balance
    assert round(trade.pnl, 8) == round(wallet_delta, 8)

    # this test closes a position, so clean up the shared store to avoid leaking the
    # closed trade into tests that assume an empty store at their start
    store.reset()
