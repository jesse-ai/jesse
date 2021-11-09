from jesse.services.db import db
from playhouse.migrate import *


def run():
    """
    Run migrations per each table and adds new fields in case they have not been added yet.
    """
    migrator = PostgresqlMigrator(db)

    _migrate_candle(migrator)
    _migrate_completed_trade(migrator)
    _migrate_daily_balance(migrator)
    _migrate_log(migrator)
    _migrate_order(migrator)
    _migrate_orderbook(migrator)
    _migrate_ticker(migrator)
    _migrate_trade(migrator)


def _migrate_candle(migrator):
    fields = {}

    candle_columns = db.get_columns('candle')

    for key, value in fields.items():
        item_exist = any(key == item.name for item in candle_columns)
        if item_exist:
            print(f'{key} field previously added to candle table.')
        else:
            migrate(
                migrator.add_column('candle', key, value)
            )
            print(f'{key} field successfully added to candle table.')


def _migrate_completed_trade(migrator):
    fields = {}

    completedtrade_columns = db.get_columns('completedtrade')

    for key, value in fields.items():
        item_exist = any(key == item.name for item in completedtrade_columns)
        if item_exist:
            print(f'{key} field previously added to completedtrade table.')
        else:
            migrate(
                migrator.add_column('completedtrade', key, value)
            )
            print(f'{key} field successfully added to completedtrade table.')


def _migrate_daily_balance(migrator):
    fields = {}

    dailybalance_columns = db.get_columns('dailybalance')

    for key, value in fields.items():
        item_exist = any(key == item.name for item in dailybalance_columns)
        if item_exist:
            print(f'{key} field previously added to dailybalance table.')
        else:
            migrate(
                migrator.add_column('dailybalance', key, value)
            )
            print(f'{key} field successfully added to dailybalance table.')


def _migrate_log(migrator):
    fields = {}

    log_columns = db.get_columns('log')

    for key, value in fields.items():
        item_exist = any(key == item.name for item in log_columns)
        if not item_exist:
            migrate(
                migrator.add_column('log', key, value)
            )
            print(f'{key} field successfully added to log table.')
        else:
            print(f'{key} field previously added to log table.')


def _migrate_order(migrator):
    fields = {
        'trade_id': UUIDField(index=True, null=True),
        'session_id': UUIDField(index=True, null=True),
        'exchange_id': CharField(null=True)
    }

    order_columns = db.get_columns('order')

    for key, value in fields.items():
        item_exist = any(key == item.name for item in order_columns)
        if not item_exist:
            migrate(
                migrator.add_column('order', key, value)
            )
            print(f'{key} field successfully added to order table.')
        else:
            print(f'{key} field previously added to order table.')


def _migrate_orderbook(migrator):
    fields = {}

    orderbook_columns = db.get_columns('orderbook')

    for key, value in fields.items():
        item_exist = any(key == item.name for item in orderbook_columns)
        if item_exist:
            print(f'{key} field previously added to orderbook table.')
        else:
            migrate(
                migrator.add_column('orderbook', key, value)
            )
            print(f'{key} field successfully added to orderbook table.')


def _migrate_ticker(migrator):
    fields = {}

    ticker_columns = db.get_columns('ticker')

    for key, value in fields.items():
        item_exist = any(key == item.name for item in ticker_columns)
        if item_exist:
            print(f'{key} field previously added to ticker table.')
        else:
            migrate(
                migrator.add_column('ticker', key, value)
            )
            print(f'{key} field successfully added to ticker table.')


def _migrate_trade(migrator):
    fields = {}

    trade_columns = db.get_columns('trade')

    for key, value in fields.items():
        item_exist = any(key == item.name for item in trade_columns)
        if item_exist:
            print(f'{key} field previously added to trade table.')
        else:
            migrate(
                migrator.add_column('trade', key, value)
            )
            print(f'{key} field successfully added to trade table.')
