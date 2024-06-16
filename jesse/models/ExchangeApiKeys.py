import peewee
from jesse.services.db import database
from jesse.models import NotificationApiKeys

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
    general_notifications_id = peewee.UUIDField(null=True)
    error_notifications_id = peewee.UUIDField(null=True)
    general_notifications: NotificationApiKeys = None
    error_notifications: NotificationApiKeys = None

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


def get_exchange_api_key(exchange_api_key_id: str) -> ExchangeApiKeys:
    exchange_api_key: ExchangeApiKeys = ExchangeApiKeys.get_or_none(ExchangeApiKeys.id == exchange_api_key_id)

    if exchange_api_key.general_notifications_id:
        exchange_api_key.general_notifications = NotificationApiKeys.get_or_none(NotificationApiKeys.id == exchange_api_key.general_notifications_id)
    if exchange_api_key.error_notifications_id:
        exchange_api_key.error_notifications = NotificationApiKeys.get_or_none(NotificationApiKeys.id == exchange_api_key.error_notifications_id)

    return exchange_api_key
