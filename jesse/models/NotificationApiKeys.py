import peewee
from jesse.services.db import database

if database.is_closed():
    database.open_connection()


class NotificationApiKeys(peewee.Model):
    id = peewee.UUIDField(primary_key=True)
    name = peewee.CharField(unique=True)
    driver = peewee.CharField()  # notification driver (Telegram, Discord, Slack)
    fields = peewee.TextField()  # for storing the fields as a JSON string
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


# if database is open, create the table
if database.is_open():
    NotificationApiKeys.create_table()
