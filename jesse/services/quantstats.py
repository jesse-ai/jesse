import os
from datetime import datetime, timedelta

import arrow
import numpy as np
import pandas as pd
import quantstats as qs

from jesse.config import config
from jesse.store import store


def quantstats_tearsheet(buy_and_hold_returns: np.ndarray) -> None:
  daily_returns = pd.Series(store.app.daily_balance).pct_change(1).values

  start_date = datetime.fromtimestamp(store.app.starting_time / 1000)
  date_list = [start_date + timedelta(days=x) for x in range(len(store.app.daily_balance))]

  returns_time_series = pd.Series(daily_returns, index=pd.to_datetime(list(date_list)))

  mode = config['app']['trading_mode']
  modes = {
    'backtest': ['BT', 'Backtest'],
    'livetrade': ['LT', 'LiveTrade'],
    'papertrade': ['PT', 'PaperTrade']
  }

  os.makedirs('./storage/full-reports', exist_ok=True)

  file_path = f'storage/full-reports/{modes[mode][0]}-{str(arrow.utcnow())[0:19]}.html'.replace(":", "-")

  title = f"{modes[mode][1]} → {arrow.utcnow().strftime('%d %b, %Y %H:%M:%S')}"

  qs.reports.html(returns=returns_time_series, benchmark=buy_and_hold_returns, title=title, output=file_path)

  print(f'\nFull report output saved at:\n{file_path}')
