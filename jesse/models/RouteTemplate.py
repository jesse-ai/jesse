import peewee

from jesse.services.db import database


if database.is_closed():
    database.open_connection()


class RouteTemplate(peewee.Model):
    id = peewee.UUIDField(primary_key=True)
    name = peewee.CharField(max_length=80)
    name_key = peewee.CharField(max_length=80, unique=True)
    routes = peewee.TextField()
    data_routes = peewee.TextField()
    fingerprint = peewee.CharField(max_length=64, unique=True)
    created_at = peewee.BigIntegerField()
    updated_at = peewee.BigIntegerField()
    last_used_at = peewee.BigIntegerField(index=True)

    class Meta:
        from jesse.services.db import database

        database = database.db

    def __init__(self, attributes: dict = None, **kwargs) -> None:
        peewee.Model.__init__(self, attributes=attributes, **kwargs)

        if attributes is None:
            attributes = {}

        for attribute, value in attributes.items():
            setattr(self, attribute, value)
