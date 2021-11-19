import peewee


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
        indexes = ((('timestamp', 'exchange', 'symbol'), True),)

    def __init__(self, attributes: dict = None, **kwargs) -> None:
        peewee.Model.__init__(self, attributes=attributes, **kwargs)

        if attributes is None:
            attributes = {}

        for a, value in attributes.items():
            setattr(self, a, value)
