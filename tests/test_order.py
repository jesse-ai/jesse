from jesse.models import Order
import jesse.helpers as jh
from jesse.enums import order_types, sides, order_statuses


def test_cancel_order():
    order = Order({
        'id': jh.generate_unique_id(),
        'symbol': 'BTCUSD',
        'type': order_types.LIMIT,
        'price': 129.33,
        'qty': 10.2041,
        'side': sides.BUY,
        'status': order_statuses.ACTIVE,
        'created_at': jh.now(),
    })

    assert order.is_canceled is False

    order.cancel()

    assert order.is_canceled is True
    assert order.canceled_at == jh.now()


def test_execute_order():
    order = Order({
        'id': jh.generate_unique_id(),
        'symbol': 'BTCUSD',
        'type': order_types.LIMIT,
        'price': 129.33,
        'qty': 10.2041,
        'side': sides.BUY,
        'status': order_statuses.ACTIVE,
        'created_at': jh.now(),
    })

    assert order.is_executed is False
    assert order.executed_at is None

    order.execute()

    assert order.is_executed is True
    assert order.executed_at == jh.now()
