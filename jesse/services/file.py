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
