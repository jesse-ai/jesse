import peewee


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
        indexes = ((('timestamp', 'exchange', 'symbol'), True),)

    def __init__(self, attributes: dict = None, **kwargs) -> None:
        peewee.Model.__init__(self, attributes=attributes, **kwargs)

        if attributes is None:
            attributes = {}

        for a, value in attributes.items():
            setattr(self, a, value)

