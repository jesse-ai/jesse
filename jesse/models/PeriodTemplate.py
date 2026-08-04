import peewee
from jesse.services.db import database


if database.is_closed():
    database.open_connection()


class PeriodTemplate(peewee.Model):
    id = peewee.UUIDField(primary_key=True)

    # date range in YYYY-MM-DD format
    start_date = peewee.CharField(max_length=10)
    finish_date = peewee.CharField(max_length=10)

    # timestamps
    created_at = peewee.BigIntegerField()
    last_used_at = peewee.BigIntegerField()

    class Meta:
        from jesse.services.db import database

        database = database.db
        indexes = (
            (('start_date', 'finish_date'), True),
        )

    def __init__(self, attributes: dict = None, **kwargs) -> None:
        peewee.Model.__init__(self, attributes=attributes, **kwargs)

        if attributes is None:
            attributes = {}

        for a, value in attributes.items():
            setattr(self, a, value)
