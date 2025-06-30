from jesse.services.db import database
from playhouse.migrate import *
from jesse.enums import migration_actions
import click


def run():
    """
    Runs migrations per each table and adds new fields in case they have not been added yet.

    Accepted action types: add, drop, rename, modify_type, allow_null, deny_null
    If actions type is 'rename', you must add new field with 'old_name' key.
    To make column to not nullable, you must clean all null value of columns.
    """
    print('Checking for new database migrations...\n')

    database.open_connection()

    # create migrator
    migrator = PostgresqlMigrator(database.db)
    # run migrations
    _candle(migrator)
    _completed_trade(migrator)
    _daily_balance(migrator)
    _log(migrator)
    _order(migrator)
    _orderbook(migrator)
    _ticker(migrator)
    _trade(migrator)
    _exchange_api_keys(migrator)

    # create initial tables
    from jesse.models import Candle, ClosedTrade, Log, Order, Option
    database.db.create_tables([Candle, ClosedTrade, Log, Order])

    database.close_connection()


def _candle(migrator):
    fields = [
        {'action': migration_actions.ADD, 'name': 'timeframe', 'type': CharField(index=False, null=True)},
        {'action': migration_actions.DROP_INDEX, 'indexes': ('exchange', 'symbol', 'timestamp')},
        {'action': migration_actions.ADD_INDEX, 'indexes': ('exchange', 'symbol', 'timeframe', 'timestamp'), 'is_unique': True},
    ]

    if 'candle' in database.db.get_tables():
        candle_columns = database.db.get_columns('candle')
        _migrate(migrator, fields, candle_columns, 'candle')


def _completed_trade(migrator):
    fields = []

    if 'completedtrade' in database.db.get_tables():
        completedtrade_columns = database.db.get_columns('completedtrade')
        _migrate(migrator, fields, completedtrade_columns, 'completedtrade')


def _daily_balance(migrator):
    fields = []

    if 'dailybalance' in database.db.get_tables():
        dailybalance_columns = database.db.get_columns('dailybalance')
        _migrate(migrator, fields, dailybalance_columns, 'dailybalance')


def _log(migrator):
    fields = []

    if 'log' in database.db.get_tables():
        log_columns = database.db.get_columns('log')
        _migrate(migrator, fields, log_columns, 'log')


def _order(migrator):
    fields = [
        # {'name': 'session_id', 'type': UUIDField(index=True, null=True), 'action': migration_actions.ADD},
        # {'name': 'trade_id', 'type': UUIDField(index=True, null=True), 'action': migration_actions.ALLOW_NULL},
        # {'name': 'exchange_id', 'type': CharField(null=True), 'action': migration_actions.ALLOW_NULL},
        # {'name': 'price', 'type': FloatField(null=True), 'action': migration_actions.ALLOW_NULL},
        # {'name': 'flag', 'type': CharField(default=False), 'action': migration_actions.DROP},
        # {'name': 'role', 'type': CharField(default=False), 'action': migration_actions.DROP},
        # {'name': 'filled_qty', 'type': FloatField(default=0), 'action': migration_actions.ADD},
        # {'name': 'reduce_only', 'type': BooleanField(default=False), 'action': migration_actions.ADD},
    ]

    if 'order' in database.db.get_tables():
        order_columns = database.db.get_columns('order')
        _migrate(migrator, fields, order_columns, 'order')


def _orderbook(migrator):
    fields = []

    if 'orderbook' in database.db.get_tables():
        orderbook_columns = database.db.get_columns('orderbook')
        _migrate(migrator, fields, orderbook_columns, 'orderbook')


def _ticker(migrator):
    fields = []

    if 'ticker' in database.db.get_tables():
        ticker_columns = database.db.get_columns('ticker')
        _migrate(migrator, fields, ticker_columns, 'ticker')


def _trade(migrator):
    fields = []

    if 'trade' in database.db.get_tables():
        trade_columns = database.db.get_columns('trade')
        _migrate(migrator, fields, trade_columns, 'trade')


def _exchange_api_keys(migrator):
    fields = []

    if 'exchange_api_keys' in database.db.get_tables():
        exchange_api_keys_columns = database.db.get_columns('exchange_api_keys')
        _migrate(migrator, fields, exchange_api_keys_columns, 'exchange_api_keys')


def _migrate(migrator, fields, columns, table):
    for field in fields:
        if field['action'] in [migration_actions.ADD_INDEX, migration_actions.DROP_INDEX]:
            indexes: list = database.db.get_indexes(table)
            to_migrate_indexes: list = field['indexes']
            to_migrate_indexes_str = f'{table}_'
            for t in to_migrate_indexes:
                to_migrate_indexes_str += f'{t}_'
            to_migrate_indexes_str = to_migrate_indexes_str[:-1]
            already_exists = False
            for index in indexes:
                existing_indexes_str: list = index.name
                if to_migrate_indexes_str == existing_indexes_str:
                    already_exists = True
                    break
            if field['action'] == migration_actions.ADD_INDEX:
                if not already_exists:
                    migrate(
                        migrator.add_index(table, field['indexes'], field['is_unique'])
                    )
                    print(f'Added index {field["indexes"]} to {table}')
            if field['action'] == migration_actions.DROP_INDEX:
                if already_exists:
                    migrate(
                        migrator.drop_index(table, to_migrate_indexes_str)
                    )
                    print(f'Dropped index {field["indexes"]} from the "{table}" table')
        else: # else, fist check if the field exists
            column_name_exist = any(field['name'] == item.name for item in columns)
            if column_name_exist:
                if field['action'] == migration_actions.ADD:
                    pass
                elif field['action'] == migration_actions.DROP:
                    migrate(
                        migrator.drop_column(table, field['name'])
                    )
                    print(f"Successfully dropped '{field['name']}' column from the "'{table}'" table.")
                elif field['action'] == migration_actions.RENAME:
                    migrate(
                        migrator.rename_column(table, field['name'], field['new_name'])
                    )
                    print(f"'{field['name']}' column successfully changed to {field['new_name']} in the '{table}' table.")
                elif field['action'] == migration_actions.MODIFY_TYPE:
                    migrate(
                        migrator.alter_column_type(table, field['name'], field['type'])
                    )
                    print(
                        f"'{field['name']}' field's type was successfully changed to {field['type']} in the '{table}' table.")
                elif field['action'] == migration_actions.ALLOW_NULL:
                    migrate(
                        migrator.drop_not_null(table, field['name'])
                    )
                    print(f"'{field['name']}' column successfully updated to accept nullable values in the '{table}' table.")
                elif field['action'] == migration_actions.DENY_NULL:
                    migrate(
                        migrator.add_not_null(table, field['name'])
                    )
                    print(
                        f"'{field['name']}' column successfully updated to accept to reject nullable values in the '{table}' table.")
            # if column name doesn't not already exist
            else:
                if field['action'] == migration_actions.ADD:
                    migrate(
                        migrator.add_column(table, field['name'], field['type'])
                    )
                    print(f"'{field['name']}' column successfully added to '{table}' table.")
                else:
                    print(f"'{field['name']}' field does not exist in '{table}' table.")
