from random import randint

import jesse.helpers as jh
from jesse.enums import exchanges, sides, order_types, order_statuses
from jesse.models import Order

first_timestamp = 1552309186171


def fake_order(attributes=None):
    """

    :param attributes:
    :return:
    """
    if attributes is None:
        attributes = {}

    global first_timestamp
    first_timestamp += 60000
    exchange = exchanges.SANDBOX
    symbol = 'BTCUSD'
    side = sides.BUY
    order_type = order_types.LIMIT
    price = randint(40, 100)
    qty = randint(1, 10)
    status = order_statuses.ACTIVE
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
