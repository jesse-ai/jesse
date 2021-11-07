from jesse.services.db import db
from playhouse.migrate import *


def run():
    migrator = PostgresqlMigrator(db)

    migrate_candle(migrator)
    migrate_completed_trade(migrator)
    migrate_daily_balance(migrator)
    migrate_log(migrator)
    migrate_order(migrator)
    migrate_orderbook(migrator)
    migrate_ticker(migrator)
    migrate_trade(migrator)


def migrate_candle(migrator):
    fields = {
        #     add new fields of candles table here
    }

    candle_column = db.get_columns('candle')

    for key, value in fields.items():
        item_exist = any(key == item.name for item in candle_column)
        if not item_exist:
            migrate(
                migrator.add_column('candle', key, value)
            )
            print(f'{key} field successfully added to candle table.')
        else:
            print(f'{key} field previously added to candle table.')


def migrate_completed_trade(migrator):
    fields = {
        #     add new fields of compeletedtrade table here
    }

    completedtrade_column = db.get_columns('completedtrade')

    for key, value in fields.items():
        item_exist = any(key == item.name for item in completedtrade_column)
        if not item_exist:
            migrate(
                migrator.add_column('completedtrade', key, value)
            )
            print(f'{key} field successfully added to completedtrade table.')
        else:
            print(f'{key} field previously added to completedtrade table.')


def migrate_daily_balance(migrator):
    fields = {
        #     add new fields of dailybalance table here
    }

    dailybalance_column = db.get_columns('dailybalance')

    for key, value in fields.items():
        item_exist = any(key == item.name for item in dailybalance_column)
        if not item_exist:
            migrate(
                migrator.add_column('dailybalance', key, value)
            )
            print(f'{key} field successfully added to dailybalance table.')
        else:
            print(f'{key} field previously added to dailybalance table.')


def migrate_log(migrator):
    fields = {
        #     add new fields of log table here
    }

    log_column = db.get_columns('log')

    for key, value in fields.items():
        item_exist = any(key == item.name for item in log_column)
        if not item_exist:
            migrate(
                migrator.add_column('log', key, value)
            )
            print(f'{key} field successfully added to log table.')
        else:
            print(f'{key} field previously added to log table.')


def migrate_order(migrator):
    fields = {
        'session_id': UUIDField(index=True, null=True)
    }

    order_column = db.get_columns('order')

    for key, value in fields.items():
        item_exist = any(key == item.name for item in order_column)
        if not item_exist:
            migrate(
                migrator.add_column('order', key, value)
            )
            print(f'{key} field successfully added to order table.')
        else:
            print(f'{key} field previously added to order table.')


def migrate_orderbook(migrator):
    fields = {
        #     add new fields of orderbook table here
    }

    orderbook_column = db.get_columns('orderbook')

    for key, value in fields.items():
        item_exist = any(key == item.name for item in orderbook_column)
        if not item_exist:
            migrate(
                migrator.add_column('orderbook', key, value)
            )
            print(f'{key} field successfully added to orderbook table.')
        else:
            print(f'{key} field previously added to orderbook table.')


def migrate_ticker(migrator):
    fields = {
        #     add new fields of ticker table here
    }

    ticker_column = db.get_columns('ticker')

    for key, value in fields.items():
        item_exist = any(key == item.name for item in ticker_column)
        if not item_exist:
            migrate(
                migrator.add_column('ticker', key, value)
            )
            print(f'{key} field successfully added to ticker table.')
        else:
            print(f'{key} field previously added to ticker table.')


def migrate_trade(migrator):
    fields = {
        #     add new fields of trade table here
    }

    trade_column = db.get_columns('trade')

    for key, value in fields.items():
        item_exist = any(key == item.name for item in trade_column)
        if not item_exist:
            migrate(
                migrator.add_column('trade', key, value)
            )
            print(f'{key} field successfully added to trade table.')
        else:
            print(f'{key} field previously added to trade table.')
