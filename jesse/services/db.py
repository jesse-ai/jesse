from playhouse.postgres_ext import PostgresqlExtDatabase
from typing import Dict, List

import jesse.helpers as jh

if not jh.is_unit_testing():
    # connect to the database
    db = PostgresqlExtDatabase(jh.get_config('env.databases.postgres_name'),
                               user=jh.get_config('env.databases.postgres_username'),
                               password=jh.get_config('env.databases.postgres_password'),
                               host=str(jh.get_config('env.databases.postgres_host')),
                               port=int(jh.get_config('env.databases.postgres_port')))


    def close_connection() -> None:
        db.close()


    # connect
    db.connect()
else:
    db = None


def store_candles(candles: List[Dict]) -> None:
    from jesse.models import Candle

    Candle.insert_many(candles).on_conflict_ignore().execute()
