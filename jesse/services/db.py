from playhouse.postgres_ext import PostgresqlExtDatabase
from typing import Dict, List
import jesse.helpers as jh
from jesse.services.env import ENV_VALUES


if not jh.is_jesse_project() or jh.is_unit_testing():
    db = None

    def close_connection() -> None:
        """
        Do nothing
        """
        pass
else:
    if jh.is_jesse_project():
        keepalive_kwargs = {
            "keepalives": 1,
            "keepalives_idle": 60,
            "keepalives_interval": 10,
            "keepalives_count": 5
        }

        # connect to the database
        db = PostgresqlExtDatabase(
            ENV_VALUES['POSTGRES_NAME'],
            user=ENV_VALUES['POSTGRES_USERNAME'],
            password=ENV_VALUES['POSTGRES_PASSWORD'],
            host=ENV_VALUES['POSTGRES_HOST'],
            port=int(ENV_VALUES['POSTGRES_PORT']),
            **keepalive_kwargs
        )

        def close_connection() -> None:
            db.close()
    

        # connect
        db.connect()


def store_candles(candles: List[Dict]) -> None:
    from jesse.models import Candle

    Candle.insert_many(candles).on_conflict_ignore().execute()
