import os
from datetime import datetime, timedelta

import arrow
import pandas as pd
import quantstats as qs

from jesse.config import config
from jesse.store import store
import jesse.helpers as jh


def quantstats_tearsheet(buy_and_hold_returns: pd.Series, study_name: str) -> None:
    daily_returns = pd.Series(store.app.daily_balance).pct_change(1).values

    start_date = datetime.fromtimestamp(store.app.starting_time / 1000)
    date_index = pd.date_range(start=start_date, periods=len(store.app.daily_balance))

    returns_time_series = pd.Series(daily_returns, index=date_index)

    mode = config['app']['trading_mode']
    modes = {
        'backtest': ['BT', 'Backtest'],
        'livetrade': ['LT', 'LiveTrade'],
        'papertrade': ['PT', 'PaperTrade']
    }

    os.makedirs('./storage/full-reports', exist_ok=True)

    file_path = f'storage/full-reports/{jh.get_session_id()}.html'.replace(":", "-")

    title = f"{modes[mode][1]} → {arrow.utcnow().strftime('%d %b, %Y %H:%M:%S')} → {study_name}"

    try:
        qs.reports.html(returns=returns_time_series, periods_per_year=365, benchmark=buy_and_hold_returns, title=title, output=file_path)
    except IndexError:
        qs.reports.html(returns=returns_time_series, periods_per_year=365, title=title, output=file_path)
    except:
        raise
