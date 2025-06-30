import peewee
import jesse.helpers as jh
import numpy as np
import threading


class Trade(peewee.Model):
    id = peewee.UUIDField(primary_key=True)
    # timestamp in milliseconds
    timestamp = peewee.BigIntegerField()

    price = peewee.FloatField()

    buy_qty = peewee.FloatField()
    sell_qty = peewee.FloatField()

    buy_count = peewee.IntegerField()
    sell_count = peewee.IntegerField()

    symbol = peewee.CharField()
    exchange = peewee.CharField()

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

def store_trade_into_db(exchange: str, symbol: str, trade: np.ndarray) -> None:
    return
    d = {
        'id': jh.generate_unique_id(),
        'timestamp': trade[0],
        'price': trade[1],
        'buy_qty': trade[2],
        'sell_qty': trade[3],
        'buy_count': trade[4],
        'sell_count': trade[5],
        'symbol': symbol,
        'exchange': exchange,
    }

    def async_save() -> None:
        Trade.insert(**d).on_conflict_ignore().execute()
        print(
            jh.color(
                f'trade: {jh.timestamp_to_time(d["timestamp"])}-{exchange}-{symbol}: {trade}',
                'green'
            )
        )

    # async call
    threading.Thread(target=async_save).start()