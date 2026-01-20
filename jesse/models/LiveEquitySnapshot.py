import peewee
from jesse.services.db import database


if database.is_closed():
    database.open_connection()


class LiveEquitySnapshot(peewee.Model):
    session_id = peewee.UUIDField()
    timestamp = peewee.BigIntegerField()
    currency = peewee.CharField()
    equity = peewee.DoubleField()

    class Meta:
        from jesse.services.db import database

        database = database.db
        indexes = (
            (('session_id', 'timestamp'), True),  # Unique constraint
        )
        primary_key = peewee.CompositeKey('session_id', 'timestamp')

    def __init__(self, attributes: dict = None, **kwargs) -> None:
        peewee.Model.__init__(self, attributes=attributes, **kwargs)

        if attributes is None:
            attributes = {}

        for a, value in attributes.items():
            setattr(self, a, value)


# if database is open, create the table
if database.is_open():
    LiveEquitySnapshot.create_table()

