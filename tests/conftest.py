import datetime
import sqlite3


def pytest_configure(config):
    # Route tests share the fully registered app, while production CLI imports
    # stay lightweight until startup has reserved its port and prepared services.
    import jesse.app

    # SQLite unit fixtures retain the standard ISO format without Python 3.12's
    # deprecated implicit datetime adapter. Production PostgreSQL is unaffected.
    sqlite3.register_adapter(datetime.datetime, lambda value: value.isoformat(' '))

    config.addinivalue_line(
        'markers',
        'slow: long-running regression backtests (deselect with -m "not slow")',
    )
