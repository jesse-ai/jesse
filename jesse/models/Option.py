import peewee

import jesse.helpers as jh
from jesse.services.db import db


class Option(peewee.Model):
    id = peewee.UUIDField(primary_key=True)
    updated_at = peewee.BigIntegerField()
    type = peewee.CharField()
    json = peewee.TextField()

    class Meta:
        database = db

    def __init__(self, attributes=None, **kwargs) -> None:
        peewee.Model.__init__(self, attributes=attributes, **kwargs)

        if attributes is None:
            attributes = {}

        for a in attributes:
            setattr(self, a, attributes[a])


if not jh.is_unit_testing():
    # create the table
    Option.create_table()
