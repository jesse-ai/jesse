import peewee


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
        indexes = ((('timestamp', 'exchange', 'symbol'), True),)

    def __init__(self, attributes: dict = None, **kwargs) -> None:
        peewee.Model.__init__(self, attributes=attributes, **kwargs)

        if attributes is None:
            attributes = {}

        for a, value in attributes.items():
            setattr(self, a, value)
