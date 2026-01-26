import threading
from typing import Optional

from playhouse.pool import PooledPostgresqlExtDatabase
import jesse.helpers as jh
from jesse.services.env import ENV_VALUES


class Database:
    """
    Database connection manager with connection pooling and automatic reconnection.

    This class addresses several reliability issues:
    1. Stale connection detection - validates connections before reuse
    2. Automatic reconnection - handles server-side disconnections gracefully
    3. Thread safety - uses locking for multi-threaded environments (live trading)
    4. Connection pooling - efficiently manages database connections

    Compatible with both direct PostgreSQL connections and connection poolers
    like PgBouncer.
    """

    # Connection pool settings
    # These defaults work well for both direct PostgreSQL and PgBouncer setups
    MAX_CONNECTIONS = 8          # Max pooled connections
    STALE_TIMEOUT = 300          # Seconds before a connection is considered stale (5 min)
    CONNECTION_TIMEOUT = 10      # Seconds to wait for a connection from the pool

    def __init__(self):
        self.db: Optional[PooledPostgresqlExtDatabase] = None
        self._lock = threading.RLock()  # Reentrant lock for thread safety

    def is_closed(self) -> bool:
        if self.db is None:
            return True
        return self.db.is_closed()

    def is_open(self) -> bool:
        if self.db is None:
            return False
        return not self.db.is_closed()

    def close_connection(self) -> None:
        with self._lock:
            if self.db:
                self.db.close()
                self.db = None

    def _validate_connection(self) -> bool:
        """
        Validate that the current connection is actually alive.

        The db.is_closed() method only checks client-side state and cannot detect
        server-side disconnections (e.g., PostgreSQL restart, network issues,
        PgBouncer recycling connections, idle timeouts).

        Returns:
            True if connection is valid, False otherwise.
        """
        if self.db is None:
            return False
        try:
            self.db.execute_sql('SELECT 1')
            return True
        except Exception:
            return False

    def open_connection(self) -> None:
        """
        Open a database connection with automatic validation and reconnection.

        This method is thread-safe and handles:
        - Stale connection detection via SELECT 1 validation
        - Automatic reconnection when server closes the connection
        - Connection pooling for efficient resource usage
        """
        if not jh.is_jesse_project() or jh.is_unit_testing():
            return

        with self._lock:
            # If we already have a connection object, validate it's still alive
            if self.db is not None:
                if self._validate_connection():
                    return
                # Connection is stale, close and recreate
                try:
                    self.db.close()
                except Exception:
                    pass  # Ignore errors when closing stale connection
                self.db = None

            # TCP keepalive settings to detect dead connections faster
            # These are particularly important for long-running processes
            options = {
                "keepalives": 1,              # Enable TCP keepalives
                "keepalives_idle": 60,        # Start probing after 60s idle
                "keepalives_interval": 10,    # Probe every 10s
                "keepalives_count": 5,        # Give up after 5 failed probes
                "connect_timeout": 10,        # Connection timeout in seconds
            }

            # Use PooledPostgresqlExtDatabase for better connection management:
            # - Automatic connection validation before reuse
            # - Handles stale connections gracefully
            # - Thread-safe connection pool
            # - Works with both direct PostgreSQL and PgBouncer
            self.db = PooledPostgresqlExtDatabase(
                ENV_VALUES['POSTGRES_NAME'],
                user=ENV_VALUES['POSTGRES_USERNAME'],
                password=ENV_VALUES['POSTGRES_PASSWORD'],
                host=ENV_VALUES['POSTGRES_HOST'],
                port=int(ENV_VALUES['POSTGRES_PORT']),
                sslmode=ENV_VALUES.get('POSTGRES_SSLMODE', 'disable'),
                max_connections=self.MAX_CONNECTIONS,
                stale_timeout=self.STALE_TIMEOUT,
                timeout=self.CONNECTION_TIMEOUT,
                **options
            )

            self.db.connect()


database = Database()
