from playhouse.postgres_ext import PostgresqlExtDatabase
from typing import Dict, List

import jesse.helpers as jh
from jesse.services.env import ENV_VALUES

if not jh.is_unit_testing():
    # connect to the database
    db = PostgresqlExtDatabase(
        ENV_VALUES['POSTGRES_NAME'],
        user=ENV_VALUES['POSTGRES_USERNAME'],
        password=ENV_VALUES['POSTGRES_PASSWORD'],
        host=ENV_VALUES['POSTGRES_HOST'],
        port=int(ENV_VALUES['POSTGRES_PORT'])
    )


    def close_connection() -> None:
        db.close()


    # connect
    db.connect()
else:
    db = None


def store_candles(candles: List[Dict]) -> None:
    from jesse.models import Candle

    Candle.insert_many(candles).on_conflict_ignore().execute()
