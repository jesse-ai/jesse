from jesse.testing_utils import single_route_backtest


def test_remaining_qty_property():
    set_up()

    buy_order = Order({
        'id': jh.generate_unique_id(),
        'symbol': 'BTC-USDT',
        'exchange': 'Sandbox',
        'type': order_types.LIMIT,
        'price': 129.33,
        'qty': 10,
        'filled_qty': 4,
        'side': sides.BUY,
        'status': order_statuses.ACTIVE,
        'created_at': jh.now_to_timestamp(),
    })
    assert buy_order.remaining_qty == 6

    sell_order = Order({
        'id': jh.generate_unique_id(),
        'symbol': 'BTC-USDT',
        'exchange': 'Sandbox',
        'type': order_types.LIMIT,
        'price': 129.33,
        'qty': -10,
        'filled_qty': -4,
        'side': sides.SELL,
        'status': order_statuses.ACTIVE,
        'created_at': jh.now_to_timestamp(),
    })
    assert sell_order.remaining_qty == -6


def test_order_is_stop_loss_property():
    single_route_backtest('TestOrderIsStopLossProperty')


def test_order_is_take_profit_property():
    single_route_backtest('TestOrderIsTakeProfitProperty')


def test_order_value_property():
    single_route_backtest('TestOrderValueProperty')
