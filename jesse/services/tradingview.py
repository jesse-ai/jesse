import os

import jesse.helpers as jh
from jesse.store import store


def tradingview_logs(study_name:str=None, mode=None, now=None) -> None:

    tv_text = '//@version=4\nstrategy("{}", overlay=true, initial_capital=10000, commission_type=strategy.commission.percent, commission_value=0.2)\n'.format(
        study_name)

    for i, t in enumerate(store.completed_trades.trades[::-1][:]):
        tv_text += '\n'
        for j, o in enumerate(t.orders):
            when = "time_close == {}".format(int(o.executed_at))
            if int(o.executed_at) % (jh.timeframe_to_one_minutes(t.timeframe) * 60_000) != 0:
                when = "time_close >= {} and time_close - {} < {}" \
                    .format(int(o.executed_at),
                            int(o.executed_at) + jh.timeframe_to_one_minutes(t.timeframe) * 60_000,
                            jh.timeframe_to_one_minutes(t.timeframe) * 60_000)
            if j == len(t.orders) - 1:
                tv_text += 'strategy.close("{}", when = {})\n'.format(i, when)
            else:
                tv_text += 'strategy.order("{}", {}, {}, {}, when = {})\n'.format(
                    i, 1 if t.type == 'long' else 0, abs(o.qty), o.price, when
                )

    path = 'storage/trading-view-pine-editor/{}-{}.txt'.format(mode, now).replace(":", "-")
    os.makedirs('./storage/trading-view-pine-editor', exist_ok=True)
    with open(path, 'w+') as outfile:
        outfile.write(tv_text)

    print('\nPine-editor output saved at: \n{}'.format(path))
