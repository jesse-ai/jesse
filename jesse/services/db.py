from playhouse.postgres_ext import PostgresqlExtDatabase
from typing import Dict, List
import jesse.helpers as jh
from jesse.services.env import ENV_VALUES


def store_candles(candles: List[Dict]) -> None:
    from jesse.models import Candle
    Candle.insert_many(candles).on_conflict_ignore().execute()


# refactor above code into a class
class Database:
    def __init__(self):
        self.db: PostgresqlExtDatabase = None

    def close_connection(self) -> None:
        if self.db:
            self.db.close()

    def open_connection(self) -> None:
        if not jh.is_jesse_project() or jh.is_unit_testing():
            return

        keepalive_kwargs = {
            "keepalives": 1,
            "keepalives_idle": 60,
            "keepalives_interval": 10,
            "keepalives_count": 5
        }

        self.db = PostgresqlExtDatabase(
            ENV_VALUES['POSTGRES_NAME'],
            user=ENV_VALUES['POSTGRES_USERNAME'],
            password=ENV_VALUES['POSTGRES_PASSWORD'],
            host=ENV_VALUES['POSTGRES_HOST'],
            port=int(ENV_VALUES['POSTGRES_PORT']),
            **keepalive_kwargs
        )

        # connect to the database
        self.db.connect()


database = Database()
