import peewee
from jesse.services.db import database


if database.is_closed():
    database.open_connection()


class ExchangeApiKeys(peewee.Model):
    id = peewee.UUIDField(primary_key=True)
    exchange_name = peewee.CharField()
    name = peewee.CharField(unique=True)
    api_key = peewee.CharField(unique=True)
    api_secret = peewee.CharField(unique=True)
    additional_fields = peewee.TextField()
    created_at = peewee.BigIntegerField()

    class Meta:
        from jesse.services.db import database

        database = database.db

    def __init__(self, attributes=None, **kwargs) -> None:
        peewee.Model.__init__(self, attributes=attributes, **kwargs)

        if attributes is None:
            attributes = {}

        for a in attributes:
            setattr(self, a, attributes[a])


# if database is open, create the table
if database.is_open():
    ExchangeApiKeys.create_table()
