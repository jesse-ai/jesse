import datetime
import csv
import json
import os

import arrow

from jesse.config import config
from jesse.services.tradingview import tradingview_logs
from jesse.store import store
import jesse.helpers as jh


def store_logs(study_name: str = '', export_json: bool = False, export_tradingview: bool = False, export_csv: bool = False) -> None:
    mode = config['app']['trading_mode']

    now = str(arrow.utcnow())[0:19]
    study_name = jh.get_session_id()
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

    # store output for TradingView.com's pine-editor
    if export_tradingview:
        tradingview_logs(study_name)

    # also write a CSV file
    if export_csv:
        path = f'storage/csv/{study_name}.csv'
        os.makedirs('./storage/csv', exist_ok=True)

        with open(path, 'w', newline='') as outfile:
            wr = csv.writer(outfile, quoting=csv.QUOTE_ALL)

            # header of CSV file
            wr.writerow(trades_json['trades'][0].keys())
            for t in trades_json['trades']:
                t['holding_period'] = datetime.timedelta(seconds=t['holding_period'])
                t['opened_at'] = datetime.datetime.fromtimestamp(t['opened_at']/1000)
                t['closed_at'] = datetime.datetime.fromtimestamp(t['closed_at']/1000)
                t['entry_candle_timestamp'] = datetime.datetime.fromtimestamp(t['entry_candle_timestamp']/1000)
                t['exit_candle_timestamp'] = datetime.datetime.fromtimestamp(t['exit_candle_timestamp']/1000)
                wr.writerow(t.values())
