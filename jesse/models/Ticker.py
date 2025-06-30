import peewee
import jesse.helpers as jh
import numpy as np


class Ticker(peewee.Model):
    id = peewee.UUIDField(primary_key=True)
    # timestamp in milliseconds
    timestamp = peewee.BigIntegerField()
    # the latest trades price
    last_price = peewee.FloatField()
    # the trading volume in the last 24 hours
    volume = peewee.FloatField()
    # the highest price in the last 24 hours
    high_price = peewee.FloatField()
    # the lowest price in the last 24 hours
    low_price = peewee.FloatField()
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

def store_ticker_into_db(exchange: str, symbol: str, ticker: np.ndarray) -> None:
    return
    d = {
        'id': jh.generate_unique_id(),
        'timestamp': ticker[0],
        'last_price': ticker[1],
        'high_price': ticker[2],
        'low_price': ticker[3],
        'volume': ticker[4],
        'symbol': symbol,
        'exchange': exchange,
    }

    def async_save() -> None:
        Ticker.insert(**d).on_conflict_ignore().execute()
        print(
            jh.color(f'ticker: {jh.timestamp_to_time(d["timestamp"])}-{exchange}-{symbol}: {ticker}', 'yellow')
        )

    # async call
    threading.Thread(target=async_save).start()
