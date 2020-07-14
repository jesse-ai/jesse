import peewee

import jesse.helpers as jh
from jesse.services.db import db


class Candle(peewee.Model):
    """

    """
    id = peewee.UUIDField(primary_key=True)
    timestamp = peewee.BigIntegerField()
    open = peewee.FloatField()
    close = peewee.FloatField()
    high = peewee.FloatField()
    low = peewee.FloatField()
    volume = peewee.FloatField()
    symbol = peewee.CharField()
    exchange = peewee.CharField()

    # partial candles: 5 * 1m candle = 5m candle while 1m == partial candle
    is_partial = True

    class Meta:
        database = db
        indexes = (
            (('timestamp', 'exchange', 'symbol'), True),
        )

    def __init__(self, attributes=None, **kwargs):
        peewee.Model.__init__(self, attributes=attributes, **kwargs)

        if attributes is None:
            attributes = {}

        for a in attributes:
            setattr(self, a, attributes[a])


if not jh.is_unit_testing():
    # create the table
    Candle.create_table()
