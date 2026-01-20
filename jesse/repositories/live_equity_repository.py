from typing import Optional, List
import math
import jesse.helpers as jh
from jesse.models.LiveEquitySnapshot import LiveEquitySnapshot
from jesse.services.db import database


def _ensure_db_open() -> None:
    if not database.is_open():
        database.open_connection()


def upsert_snapshot(session_id: str, timestamp: int, currency: str, equity: float) -> None:
    """
    Insert or update a single equity snapshot for the given session and minute bucket.
    Uses ON CONFLICT to ensure only one row per (session_id, timestamp).
    """
    if jh.is_unit_testing():
        return

    _ensure_db_open()

    # Peewee doesn't have native UPSERT, so we use raw SQL
    # NOTE: Backwards compatible with older schema using bucket_ms
    query_ts = """
        INSERT INTO liveequitysnapshot (session_id, "timestamp", currency, equity)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (session_id, "timestamp")
        DO UPDATE SET equity = EXCLUDED.equity, currency = EXCLUDED.currency
    """
    try:
        database.db.execute_sql(query_ts, (session_id, timestamp, currency, equity))
        return
    except Exception:
        query_bucket = """
            INSERT INTO liveequitysnapshot (session_id, bucket_ms, currency, equity)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (session_id, bucket_ms)
            DO UPDATE SET equity = EXCLUDED.equity, currency = EXCLUDED.currency
        """
        database.db.execute_sql(query_bucket, (session_id, timestamp, currency, equity))


def _choose_step_ms(from_ms: int, to_ms: int, timeframe: str, max_points: int = 1000) -> int:
    """
    Choose the step size in milliseconds based on timeframe or auto-resolution.
    """
    if timeframe == 'auto':
        # Calculate raw step needed
        duration_ms = to_ms - from_ms
        if duration_ms <= 0:
            return 60_000  # default to 1m
        
        raw_step = math.ceil(duration_ms / max_points / 60_000) * 60_000
        
        # Snap to friendly steps
        if raw_step <= 60_000:
            return 60_000  # 1m
        elif raw_step <= 300_000:
            return 300_000  # 5m
        elif raw_step <= 900_000:
            return 900_000  # 15m
        elif raw_step <= 3_600_000:
            return 3_600_000  # 1h
        else:
            return 86_400_000  # 1d
    
    # Fixed timeframes
    timeframe_map = {
        '1m': 60_000,
        '5m': 300_000,
        '15m': 900_000,
        '1h': 3_600_000,
        '1d': 86_400_000,
    }
    return timeframe_map.get(timeframe, 60_000)


def query_equity_curve(
    session_id: str,
    from_ms: Optional[int] = None,
    to_ms: Optional[int] = None,
    timeframe: str = 'auto',
    max_points: int = 1000
) -> dict:
    """
    Query equity curve with downsampling.
    Returns dict with currency and data points.
    
    Uses DISTINCT ON to return the last value per bucket.
    """
    if jh.is_unit_testing():
        return {'currency': 'USD', 'data': []}

    _ensure_db_open()

    # Default time range
    if from_ms is None:
        from_ms = 0
    if to_ms is None:
        # IMPORTANT: in API/server context jh.now() can return store.app.time (stale).
        # We need a fresh wall-clock timestamp for querying DB time-series.
        to_ms = jh.now(True)

    step_ms = _choose_step_ms(from_ms, to_ms, timeframe, max_points)

    # Query using DISTINCT ON for downsampling (avoid relying on SELECT alias in DISTINCT ON)
    query_ts = """
        SELECT DISTINCT ON ((( "timestamp" / %s) * %s))
            (( "timestamp" / %s) * %s) AS grp_ms,
            "timestamp",
            currency,
            equity
        FROM liveequitysnapshot
        WHERE session_id = %s
          AND "timestamp" >= %s
          AND "timestamp" <= %s
        ORDER BY (( "timestamp" / %s) * %s), "timestamp" DESC
    """

    try:
        cursor = database.db.execute_sql(
            query_ts,
            (step_ms, step_ms, step_ms, step_ms, session_id, from_ms, to_ms, step_ms, step_ms)
        )
    except Exception:
        # Backwards compatible with older schema using bucket_ms
        query_bucket = """
            SELECT DISTINCT ON ((( bucket_ms / %s) * %s))
                (( bucket_ms / %s) * %s) AS grp_ms,
                bucket_ms,
                currency,
                equity
            FROM liveequitysnapshot
            WHERE session_id = %s
              AND bucket_ms >= %s
              AND bucket_ms <= %s
            ORDER BY (( bucket_ms / %s) * %s), bucket_ms DESC
        """
        cursor = database.db.execute_sql(
            query_bucket,
            (step_ms, step_ms, step_ms, step_ms, session_id, from_ms, to_ms, step_ms, step_ms)
        )
    
    rows = cursor.fetchall()
    
    if not rows:
        return {'currency': 'USD', 'data': []}
    
    # Extract currency from first row
    currency = rows[0][2] if len(rows) > 0 else 'USD'
    
    # Build data points
    data = []
    for row in rows:
        data.append({
            'time': int(row[1] / 1000),  # Convert ms to seconds for chart
            'value': round(row[3], 2),
            # Match backtest equity curve primary color (Portfolio series)
            'color': '#818CF8'
        })
    
    return {
        'currency': currency,
        'data': data
    }


def get_session_equity_count(session_id: str) -> int:
    """
    Get the total number of equity snapshots for a session.
    Useful for debugging/monitoring.
    """
    if jh.is_unit_testing():
        return 0

    _ensure_db_open()

    try:
        return LiveEquitySnapshot.select().where(
            LiveEquitySnapshot.session_id == session_id
        ).count()
    except Exception:
        return 0

