import csv
import json
import os

import arrow

from jesse.config import config
from jesse.services.tradingview import tradingview_logs
from jesse.store import store
import jesse.helpers as jh


def store_logs(export_json: bool = False, export_tradingview: bool = False, export_csv: bool = False) -> dict:
    if store.completed_trades.count == 0:
        return {
            'json': None,
            'tradingview': None,
            'csv': None
        }

    result = {}
    file_name = jh.get_session_id()
    trades_json = {'trades': [], 'considering_timeframes': config['app']['considering_timeframes']}
    for t in store.completed_trades.trades:
        trades_json['trades'].append(t.to_json)

    if export_json:
        path = f'storage/json/{file_name}.json'

        os.makedirs('./storage/json', exist_ok=True)
        with open(path, 'w+') as outfile:
            def set_default(obj):
                if isinstance(obj, set):
                    return list(obj)
                raise TypeError

            json.dump(trades_json, outfile, default=set_default)
            result['json'] = path

    # store output for TradingView.com's pine-editor
    if export_tradingview:
        result['tradingview'] = tradingview_logs(file_name)

    # also write a CSV file
    if export_csv:
        path = f'storage/csv/{file_name}.csv'
        os.makedirs('./storage/csv', exist_ok=True)

        with open(path, 'w', newline='') as outfile:
            wr = csv.writer(outfile, quoting=csv.QUOTE_ALL)

            for i, t in enumerate(trades_json['trades']):
                if i == 0:
                    # header of CSV file
                    wr.writerow(t.keys())

                wr.writerow(t.values())

            result['csv'] = path

    return result
