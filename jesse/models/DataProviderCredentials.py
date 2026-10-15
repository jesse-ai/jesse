import peewee

from jesse.services.db import database


if database.is_closed():
    database.open_connection()


class DataProviderCredentials(peewee.Model):
    """Stores one local credential payload for each historical data provider."""

    provider_id = peewee.CharField(primary_key=True, max_length=100)
    credentials = peewee.TextField()
    created_at = peewee.BigIntegerField()
    updated_at = peewee.BigIntegerField()

    class Meta:
        database = database.db
        table_name = 'data_provider_credentials'
