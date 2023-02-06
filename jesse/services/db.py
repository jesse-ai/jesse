from playhouse.postgres_ext import PostgresqlExtDatabase
import jesse.helpers as jh
from jesse.services.env import ENV_VALUES


# refactor above code into a class
class Database:
    def __init__(self):
        self.db: PostgresqlExtDatabase = None

    def is_closed(self) -> bool:
        if self.db is None:
            return True
        return self.db.is_closed()

    def is_open(self) -> bool:
        if self.db is None:
            return False
        return not self.db.is_closed()

    def close_connection(self) -> None:
        if self.db:
            self.db.close()
            self.db = None

    def open_connection(self) -> None:
        if not jh.is_jesse_project() or jh.is_unit_testing():
            return

        # if it's not None, then we already have a connection
        if self.db is not None:
            return

        options = {
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
            sslmode=ENV_VALUES.get('POSTGRES_SSLMODE', 'disable'),
            **options
        )

        # connect to the database
        self.db.connect()


database = Database()
