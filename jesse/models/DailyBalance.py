import peewee


class DailyBalance(peewee.Model):
    id = peewee.UUIDField(primary_key=True)
    timestamp = peewee.BigIntegerField()
    identifier = peewee.CharField(null=True)
    exchange = peewee.CharField()
    asset = peewee.CharField()
    balance = peewee.FloatField()

    class Meta:
        from jesse.services.db import database

        database = database.db
        indexes = (
            (('identifier', 'exchange', 'timestamp', 'asset'), True),
            (('identifier', 'exchange'), False),
        )

    def __init__(self, attributes: dict = None, **kwargs) -> None:
        peewee.Model.__init__(self, attributes=attributes, **kwargs)

        if attributes is None:
            attributes = {}

        for a, value in attributes.items():
            setattr(self, a, value)
