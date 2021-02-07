import csv
import json
import os

import arrow

from jesse.config import config
from jesse.services.tradingview import tradingview_logs
from jesse.store import store


def store_logs(export_json: bool = False, export_tradingview: bool = False, export_csv: bool = False) -> None:
    # store trades
    mode = config['app']['trading_mode']

    now = str(arrow.utcnow())[0:19]
    study_name = '{}-{}'.format(mode, now).replace(":", "-")
    path = 'storage/json/{}.json'.format(study_name)
    trades_json = {'trades': [], 'considering_timeframes': config['app']['considering_timeframes']}
    for t in store.completed_trades.trades:
        trades_json['trades'].append(t.toJSON())

    if export_json:
        os.makedirs('./storage/json', exist_ok=True)
        with open(path, 'w+') as outfile:
            json.dump(trades_json, outfile)

        print('\nJSON output saved at: \n{}'.format(path))

    # store output for TradingView.com's pine-editor
    if export_tradingview:
        tradingview_logs(study_name, mode, now)

    # also write a CSV file
    if export_csv:
        path = 'storage/csv/{}.csv'.format(study_name)
        os.makedirs('./storage/csv', exist_ok=True)

        with open(path, 'w', newline='') as outfile:
            wr = csv.writer(outfile, quoting=csv.QUOTE_ALL)

            for i, t in enumerate(trades_json['trades']):
                if i == 0:
                    # header of CSV file
                    wr.writerow(t.keys())

                wr.writerow(t.values())

        print('\nCSV output saved at: \n{}'.format(path))
