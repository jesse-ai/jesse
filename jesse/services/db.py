import re

from playhouse.postgres_ext import PostgresqlExtDatabase

import jesse.helpers as jh
from jesse.services.env import ENV_VALUES


def postgres_schema() -> str:
    """Return the configured PostgreSQL schema after validating its SQL identifier."""
    schema = str(ENV_VALUES.get('POSTGRES_SCHEMA') or 'public')
    # The schema is inserted into PostgreSQL's search_path, so reject unsafe names.
    if not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_]*', schema):
        raise ValueError(f'Invalid PostgreSQL schema name: {schema}')
    return schema


class Database:
    """Own the shared PostgreSQL connection used by Jesse's models and services."""

    def __init__(self):
        self.db: PostgresqlExtDatabase = None

    def is_closed(self) -> bool:
        """Return whether there is no active database connection."""
        if self.db is None:
            return True
        return self.db.is_closed()

    def is_open(self) -> bool:
        """Return whether the database connection exists and is open."""
        if self.db is None:
            return False
        return not self.db.is_closed()

    def close_connection(self) -> None:
        """Close the current connection and clear the stored database instance."""
        if self.db:
            self.db.close()
            self.db = None

    def open_connection(self) -> None:
        """Create Jesse's PostgreSQL connection when the current process needs one."""
        # Non-project commands and unit tests do not use the application database.
        if not jh.is_jesse_project() or jh.is_unit_testing():
            return

        # Reuse the existing database instance instead of opening another connection.
        if self.db is not None:
            return

        # Keepalives help detect broken connections during long-running sessions.
        options = {
            "keepalives": 1,
            "keepalives_idle": 60,
            "keepalives_interval": 10,
            "keepalives_count": 5,
            # Unqualified model queries should use the configured Jesse schema.
            "options": f"-c search_path={postgres_schema()}",
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

        self.db.connect()


database = Database()
