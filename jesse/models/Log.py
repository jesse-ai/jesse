import peewee

import jesse.helpers as jh
from jesse.services.db import db


class Log(peewee.Model):
    id = peewee.UUIDField(primary_key=True)
    session_id = peewee.UUIDField(index=True)
    timestamp = peewee.BigIntegerField()
    message = peewee.TextField()
    # 1: info, 2: error, maybe add more in the future?
    type = peewee.SmallIntegerField()

    class Meta:
        database = db

    def __init__(self, attributes=None, **kwargs) -> None:
        peewee.Model.__init__(self, attributes=attributes, **kwargs)

        if attributes is None:
            attributes = {}

        for a in attributes:
            setattr(self, a, attributes[a])


if not jh.is_unit_testing() and jh.is_jesse_project():
    # create the table
    Log.create_table()
