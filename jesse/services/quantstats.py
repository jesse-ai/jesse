import os
from datetime import datetime, timedelta

import arrow
import quantstats as qs
import pandas as pd

from jesse.store import store
from jesse.config import config


def quantstats_tearsheet() -> None:
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

	file_path = 'storage/full-reports/{}-{}.html'.format(
		modes[mode][0], str(arrow.utcnow())[0:19]
	).replace(":", "-")

	title = '{} → {}'.format(modes[mode][1], arrow.utcnow().strftime("%d %b, %Y %H:%M:%S"))

	qs.reports.html(returns=returns_time_series, title=title, output=file_path)

	print('\nFull report output saved at:\n{}'.format(file_path))
