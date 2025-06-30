import peewee
from jesse.services.db import database


if database.is_closed():
    database.open_connection()


class DailyBalance(peewee.Model):
    id = peewee.UUIDField(primary_key=True)
    timestamp = peewee.BigIntegerField()
    identifier = peewee.CharField(null=True)
    exchange = peewee.CharField()
    asset = peewee.CharField()
    balance = peewee.FloatField()

    class Meta:
        from jesse.services.db import database

        database = database.db
        indexes = (
            (('identifier', 'exchange', 'asset', 'timestamp'), True),
            (('identifier', 'exchange'), False),
        )

    def __init__(self, attributes: dict = None, **kwargs) -> None:
        peewee.Model.__init__(self, attributes=attributes, **kwargs)

        if attributes is None:
            attributes = {}

        for a, value in attributes.items():
            setattr(self, a, value)


# if database is open, create the table
if database.is_open():
    DailyBalance.create_table()


# # # # # # # # # # # # # # # # # # # # # # # # # # # 
# # # # # # # # # DB FUNCTIONS # # # # # # # # #
# # # # # # # # # # # # # # # # # # # # # # # # # # # 

def store_daily_balance_into_db(daily_balance: dict) -> None:
    return
    def async_save():
        DailyBalance.insert(**daily_balance).execute()
        if jh.is_debugging():
            logger.info(
                f'Stored daily portfolio balance record into the database: {daily_balance["asset"]} => {jh.format_currency(round(daily_balance["balance"], 2))}'
                )

    # async call
    threading.Thread(target=async_save).start()