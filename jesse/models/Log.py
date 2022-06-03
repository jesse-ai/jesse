import peewee
from jesse.services.db import database


if database.is_closed():
    database.open_connection()


class Log(peewee.Model):
    id = peewee.UUIDField(primary_key=True)
    session_id = peewee.UUIDField(index=True)
    timestamp = peewee.BigIntegerField()
    message = peewee.TextField()
    # 1: info, 2: error, maybe add more in the future?
    type = peewee.SmallIntegerField()

    class Meta:
        from jesse.services.db import database
        database = database.db
        indexes = (
            (('session_id', 'type', 'timestamp'), False),
        )

    def __init__(self, attributes=None, **kwargs) -> None:
        peewee.Model.__init__(self, attributes=attributes, **kwargs)

        if attributes is None:
            attributes = {}

        for a in attributes:
            setattr(self, a, attributes[a])


# if database is open, create the table
if database.is_open():
    Log.create_table()
