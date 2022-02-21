import jesse.helpers as jh
from jesse.enums import sides, order_statuses
from jesse.models import Order
from jesse.enums import order_types
from .utils import set_up, single_route_backtest


def test_cancel_order():
    set_up()

    order = Order({
        'id': jh.generate_unique_id(),
        'exchange': 'Sandbox',
        'symbol': 'BTC-USDT',
        'type': order_types.LIMIT,
        'price': 129.33,
        'qty': 10.2041,
        'side': sides.BUY,
        'status': order_statuses.ACTIVE,
        'created_at': jh.now_to_timestamp(),
    })

    assert order.is_canceled is False

    order.cancel()

    assert order.is_canceled is True
    assert order.canceled_at == jh.now_to_timestamp()


def test_execute_order():
    set_up()

    order = Order({
        'id': jh.generate_unique_id(),
        'symbol': 'BTC-USDT',
        'exchange': 'Sandbox',
        'type': order_types.LIMIT,
        'price': 129.33,
        'qty': 10.2041,
        'side': sides.BUY,
        'status': order_statuses.ACTIVE,
        'created_at': jh.now_to_timestamp(),
    })

    assert order.is_executed is False
    assert order.executed_at is None

    order.execute()

    assert order.is_executed is True
    assert order.executed_at == jh.now_to_timestamp()


def test_order_is_stop_loss_property():
    single_route_backtest('TestOrderIsStopLossProperty')


def test_order_is_take_profit_property():
    single_route_backtest('TestOrderIsTakeProfitProperty')

