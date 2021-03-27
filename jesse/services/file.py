import csv
import json
import os

import arrow

from jesse.config import config
from jesse.services.tradingview import tradingview_logs
from jesse.store import store


def store_logs(export_json: bool = False, export_tradingview: bool = False, export_csv: bool = False) -> None:
    mode = config['app']['trading_mode']

    now = str(arrow.utcnow())[0:19]
    study_name = f'{mode}-{now}'.replace(":", "-")
    path = f'storage/json/{study_name}.json'
    trades_json = {'trades': [], 'considering_timeframes': config['app']['considering_timeframes']}
    for t in store.completed_trades.trades:
        trades_json['trades'].append(t.toJSON())

    if export_json:
        os.makedirs('./storage/json', exist_ok=True)
        with open(path, 'w+') as outfile:
            def set_default(obj):
                if isinstance(obj, set):
                    return list(obj)
                raise TypeError

            json.dump(trades_json, outfile, default=set_default)

        print(f'\nJSON output saved at: \n{path}')

    # store output for TradingView.com's pine-editor
    if export_tradingview:
        tradingview_logs(study_name, mode, now)

    # also write a CSV file
    if export_csv:
        path = f'storage/csv/{study_name}.csv'
        os.makedirs('./storage/csv', exist_ok=True)

        with open(path, 'w', newline='') as outfile:
            wr = csv.writer(outfile, quoting=csv.QUOTE_ALL)

            for i, t in enumerate(trades_json['trades']):
                if i == 0:
                    # header of CSV file
                    wr.writerow(t.keys())

                wr.writerow(t.values())

        print(f'\nCSV output saved at: \n{path}')
