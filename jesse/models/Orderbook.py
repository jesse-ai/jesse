import peewee

import jesse.helpers as jh
from jesse.services.db import db


class Orderbook(peewee.Model):
    id = peewee.UUIDField(primary_key=True)
    # timestamp in milliseconds
    timestamp = peewee.BigIntegerField()
    symbol = peewee.CharField()
    exchange = peewee.CharField()

    data = peewee.BlobField()

    class Meta:
        database = db
        indexes = ((('timestamp', 'exchange', 'symbol'), True),)

    def __init__(self, attributes=None, **kwargs)-> None:
        peewee.Model.__init__(self, attributes=attributes, **kwargs)

        if attributes is None:
            attributes = {}

        for a in attributes:
            setattr(self, a, attributes[a])


if not jh.is_unit_testing():
    # create the table
    Orderbook.create_table()
