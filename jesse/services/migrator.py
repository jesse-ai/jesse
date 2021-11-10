from jesse.services.db import db
from playhouse.migrate import *


def run():
    """
    Runs migrations per each table and adds new fields in case they have not been added yet.

    Accepted action types: add, drop, rename, change_data_type, change_nullable, change_not_nullable
    If actions type is rename, you must add new field with 'old_name' key.
    To make column to not nullable, you must clean all null value of columns.
    """
    migrator = PostgresqlMigrator(db)

    _candle(migrator)
    _completed_trade(migrator)
    _daily_balance(migrator)
    _log(migrator)
    _order(migrator)
    _orderbook(migrator)
    _ticker(migrator)
    _trade(migrator)


def _candle(migrator):
    fields = []

    candle_columns = db.get_columns('candle')

    _migrate(migrator, fields, candle_columns, 'candle')


def _completed_trade(migrator):
    fields = []

    completedtrade_columns = db.get_columns('completedtrade')

    _migrate(migrator, fields, completedtrade_columns, 'completedtrade')


def _daily_balance(migrator):
    fields = []

    dailybalance_columns = db.get_columns('dailybalance')

    _migrate(migrator, fields, dailybalance_columns, 'dailybalance')


def _log(migrator):
    fields = []

    log_columns = db.get_columns('log')

    _migrate(migrator, fields, log_columns, 'log')


def _order(migrator):
    fields = [
        {'name': 'trade_id', 'data_type': UUIDField(index=True, null=True), 'action': 'add'},
        {'name': 'session_id', 'data_type': UUIDField(index=True, null=True), 'action': 'add'},
        {'name': 'exchange_id', 'data_type': CharField(null=True), 'action': 'add'}
    ]

    order_columns = db.get_columns('order')

    _migrate(migrator, fields, order_columns, 'order')


def _orderbook(migrator):
    fields = []

    orderbook_columns = db.get_columns('orderbook')

    _migrate(migrator, fields, orderbook_columns, 'orderbook')


def _ticker(migrator):
    fields = []

    ticker_columns = db.get_columns('ticker')

    _migrate(migrator, fields, ticker_columns, 'ticker')


def _trade(migrator):
    fields = []

    trade_columns = db.get_columns('trade')

    _migrate(migrator, fields, trade_columns, 'trade')


def _migrate(migrator, fields, columns, table):
    for field in fields:
        item_exist = any(field['name'] == item.name for item in columns)

        if item_exist:
            if field['action'] == 'add':
                print(f"{field['name']} field previously added to {table} table.")

            elif field['action'] == 'drop':
                migrate(
                    migrator.drop_column(table, field['name'])
                )
                print(f"{field['name']} field successfully removed from {table} table.")

            elif field['action'] == 'rename':
                migrate(
                    migrator.rename_column(table, field['name'], field['new_name'])
                )
                print(f"{field['name']} field successfully change to {field['new_name']} in {table} table.")

            elif field['action'] == 'rename':
                migrate(
                    migrator.rename_column(table, field['name'], field['new_name'])
                )
                print(f"{field['name']} field successfully change to {field['new_name']} in {table} table.")

            elif field['action'] == 'change_data_type':
                migrate(
                    migrator.alter_column_type(table, field['name'], field['data_type'])
                )
                print(f"{field['name']} field successfully change to {field['data_type']} in {table} table.")

            elif field['action'] == 'change_nullable':
                migrate(
                    migrator.drop_not_null(table, field['name'])
                )
                print(f"{field['name']} field successfully change to nullable in {table} table.")

            elif field['action'] == 'change_not_nullable':
                migrate(
                    migrator.add_not_null(table, field['name'])
                )
                print(f"{field['name']} field successfully change to not nullable in {table} table.")

        else:
            if field['action'] == 'add':
                migrate(
                    migrator.add_column(table, field['name'], field['data_type'])
                )
                print(f"{field['name']} field successfully added to {table} table.")
            else:
                print(f"{field['name']} field not exist in {table} table.")
