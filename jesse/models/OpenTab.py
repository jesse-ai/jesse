import peewee
from jesse.services.db import database
import jesse.helpers as jh


if database.is_closed():
    database.open_connection()


class OpenTab(peewee.Model):
    id = peewee.UUIDField(primary_key=True)
    
    # Module name: live, backtest, optimization, monte_carlo
    module = peewee.CharField(max_length=50)
    
    # The session_id this tab references
    session_id = peewee.UUIDField()
    
    # Order index for tab ordering within the module
    order_index = peewee.IntegerField()
    
    # Timestamps
    created_at = peewee.BigIntegerField()
    updated_at = peewee.BigIntegerField()

    class Meta:
        from jesse.services.db import database

        database = database.db
        indexes = (
            (('module', 'session_id'), True),
        )

    def __init__(self, attributes: dict = None, **kwargs) -> None:
        peewee.Model.__init__(self, attributes=attributes, **kwargs)

        if attributes is None:
            attributes = {}

        for a, value in attributes.items():
            setattr(self, a, value)

