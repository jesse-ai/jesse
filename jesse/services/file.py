import csv
import json
import os

import arrow

from jesse.config import config
from jesse.services.tradingview import tradingview_logs
from jesse.store import store


def store_logs(tradingview=False):
    # store trades
    mode = config['app']['trading_mode']
    if mode == 'backtest':
        mode = 'BT'
    if mode == 'livetrade':
        mode = 'LT'
    if mode == 'papertrade':
        mode = 'PT'

    now = str(arrow.utcnow())[0:19]
    study_name = '{}-{}'.format(mode, now)
    path = './storage/logs/trades/{}-{}.json'.format(mode, now).replace(":", "-")
    trades_json = {'trades': []}
    for t in store.completed_trades.trades:
        trades_json['trades'].append(t.toJSON())

    os.makedirs('./storage/logs/trades', exist_ok=True)
    with open(path, 'w+') as outfile:
        json.dump(trades_json, outfile)

    # store output for TradingView.com's pine-editor
    if tradingview:
        tradingview_logs(study_name, mode, now)

    # also write a CSV file
    if config['app']['csv_mode']:
        path = './storage/csv/{}-{}.csv'.format(mode, now).replace(":", "-")
        os.makedirs('./storage/csv', exist_ok=True)

        with open(path, 'w', newline='') as outfile:
            wr = csv.writer(outfile, quoting=csv.QUOTE_ALL)

            for i, t in enumerate(trades_json['trades']):
                if i == 0:
                    # header of CSV file
                    wr.writerow(t.keys())

                wr.writerow(t.values())