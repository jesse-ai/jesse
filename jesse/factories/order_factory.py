from random import randint

import jesse.helpers as jh
from jesse.enums import Exchanges, Side, OrderType, OrderStatus
from jesse.models import Order

first_timestamp = 1552309186171


def fake_order(attributes: dict = None) -> Order:
    """

    :param attributes:
    :return:
    """
    if attributes is None:
        attributes = {}

    global first_timestamp
    first_timestamp += 60000
    exchange = Exchanges.SANDBOX
    symbol = 'BTC-USD'
    side = Side.BUY
    order_type = OrderType.LIMIT
    price = randint(40, 100)
    qty = randint(1, 10)
    status = OrderStatus.ACTIVE
    created_at = first_timestamp

    return Order({
        "id": jh.generate_unique_id(),
        'symbol': attributes.get('symbol', symbol),
        'exchange': attributes.get('exchange', exchange),
        'side': attributes.get('side', side),
        'type': attributes.get('type', order_type),
        'qty': attributes.get('qty', qty),
        'price': attributes.get('price', price),
        'status': attributes.get('status', status),
        'created_at': attributes.get('created_at', created_at),
    })
