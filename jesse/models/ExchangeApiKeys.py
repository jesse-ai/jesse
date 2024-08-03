import json
import peewee
from jesse.services.db import database

if database.is_closed():
    database.open_connection()


class ExchangeApiKeys(peewee.Model):
    id = peewee.UUIDField(primary_key=True)
    exchange_name = peewee.CharField()
    name = peewee.CharField(unique=True)
    api_key = peewee.CharField()
    api_secret = peewee.CharField()
    additional_fields = peewee.TextField()
    created_at = peewee.DateTimeField()

    class Meta:
        from jesse.services.db import database

        database = database.db

    def __init__(self, attributes=None, **kwargs) -> None:
        peewee.Model.__init__(self, attributes=attributes, **kwargs)

        if attributes is None:
            attributes = {}

        for a in attributes:
            setattr(self, a, attributes[a])

    def get_additional_fields(self) -> dict:
        return json.loads(self.additional_fields)


# if database is open, create the table
if database.is_open():
    ExchangeApiKeys.create_table()
