import json
import arrow
import os

from jesse.config import config
from jesse.store import store
import jesse.helpers as jh


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
        tv_text = '//@version=4\nstrategy("{}", overlay=true, initial_capital=10000, commission_type=strategy.commission.percent, commission_value=0.2)\n'.format(study_name)

        for i, t in enumerate(store.completed_trades.trades[::-1][:]):
            tv_text += '\n'
            for j, o in enumerate(t.orders):
                tv_text += '\nnext_timestamp{}{} = time + {}'.format(
                    i, j,
                    jh.timeframe_to_one_minutes(t.timeframe) * 60_000
                )
                tv_text += '\nwhen{}{} = {} >= time and {} < next_timestamp{}{}'.format(
                    i, j,
                    o.executed_at,
                    o.executed_at,
                    i, j
                )
                # if it's last order, it is the closing order
                if j == len(t.orders) - 1:
                    tv_text += '\nstrategy.close("{}", when = when{}{}, comment = "close trade with {} {}")\n'.format(
                        i, i, j, o.side, o.type,
                    )
                else:
                    tv_text += '\nstrategy.order("{}", strategy.{}, {}, {}, comment = "{}", when = when{}{} )\n'.format(
                        i, t.type, abs(o.qty), o.price, o.side + " " + o.type, i, j
                    )

        path = 'storage/trading-view-pine-editor/{}-{}.txt'.format(mode, now).replace(":", "-")
        os.makedirs('./storage/trading-view-pine-editor', exist_ok=True)
        with open(path, 'w+') as outfile:
            outfile.write(tv_text)
        print('Pine-editor output saved at: \n{}'.format(path))
