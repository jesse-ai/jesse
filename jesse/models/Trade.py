import peewee

import jesse.helpers as jh
from jesse.services.db import db


class Trade(peewee.Model):
    """

    """
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
        database = db
        indexes = ((('timestamp', 'exchange', 'symbol'), True),)

    def __init__(self, attributes=None, **kwargs):
        peewee.Model.__init__(self, attributes=attributes, **kwargs)

        if attributes is None:
            attributes = {}

        for a in attributes:
            setattr(self, a, attributes[a])


if not jh.is_unit_testing():
    # create the table
    Trade.create_table()
