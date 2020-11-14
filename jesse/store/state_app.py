import arrow


class AppState:
    time = arrow.utcnow().int_timestamp * 1000
    starting_time = None
    daily_balance = []

    # used as placeholders for detecting open trades metrics
    total_open_trades = 0
    total_open_pl = 0
