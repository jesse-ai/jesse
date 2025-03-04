import peewee
import jesse.helpers as jh
import numpy as np


class Orderbook(peewee.Model):
    id = peewee.UUIDField(primary_key=True)
    # timestamp in milliseconds
    timestamp = peewee.BigIntegerField()
    symbol = peewee.CharField()
    exchange = peewee.CharField()

    data = peewee.BlobField()

    class Meta:
        from jesse.services.db import database

        database = database.db
        indexes = ((('exchange', 'symbol', 'timestamp'), True),)

    def __init__(self, attributes: dict = None, **kwargs) -> None:
        peewee.Model.__init__(self, attributes=attributes, **kwargs)

        if attributes is None:
            attributes = {}

        for a, value in attributes.items():
            setattr(self, a, value)


# # # # # # # # # # # # # # # # # # # # # # # # # # # 
# # # # # # # # # DB FUNCTIONS # # # # # # # # #
# # # # # # # # # # # # # # # # # # # # # # # # # # # 

def store_orderbook_into_db(exchange: str, symbol: str, orderbook: np.ndarray) -> None:
    return
    d = {
        'id': jh.generate_unique_id(),
        'timestamp': jh.now_to_timestamp(),
        'data': orderbook.dumps(),
        'symbol': symbol,
        'exchange': exchange,
    }

    def async_save() -> None:
        Orderbook.insert(**d).on_conflict_ignore().execute()
        print(
            jh.color(
                f'orderbook: {jh.timestamp_to_time(d["timestamp"])}-{exchange}-{symbol}: [{orderbook[0][0][0]}, {orderbook[0][0][1]}], [{orderbook[1][0][0]}, {orderbook[1][0][1]}]',
                'magenta'
            )
        )

    # async call
    threading.Thread(target=async_save).start()