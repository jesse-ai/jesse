import os

import jesse.helpers as jh
from jesse.store import store

def add_label_with_text(order, text_to_add, time, operation) -> str:
    y_text = 'low+(low*16)'
    label_var_name = 'label_close'
    text_color = 'color.purple'
    label_color = 'color.purple'
    label_text = ''

    if operation == 'buy':
        y_text = 'low'
        label_var_name = 'label_buy'
        text_color = 'color.blue'
        label_color = 'color.blue'

    if text_to_add != '':
        label_text = text_to_add.encode("unicode_escape").decode("utf-8")

    text = 'var '+label_var_name+str(order)+' = label.new(x='+str(int(time))+', y='+y_text+', xloc=xloc.bar_time, text="'+label_text+'", style=label.style_diamond, textalign=text.align_left, textcolor='+text_color+', size=size.normal, color='+label_color+')'
    text += '\n'
    return text

def tradingview_logs(study_name=None, mode=None, now=None):
    """

    :param study_name:
    :param mode:
    :param now:
    """
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

            label_with_text = ''
            if j == len(t.orders) - 1:
                tv_text += 'strategy.close("{}", when = {})\n'.format(i, when)
                label_with_text = add_label_with_text(i, o.description, o.executed_at, 'close')
            else:
                tv_text += 'strategy.order("{}", {}, {}, {}, when = {})\n'.format(
                    i, 1 if t.type == 'long' else 0, abs(o.qty), o.price, when
                )
                label_with_text = add_label_with_text(i, o.description, o.executed_at, 'buy')
            tv_text += label_with_text

    path = 'storage/trading-view-pine-editor/{}-{}.txt'.format(mode, now).replace(":", "-")
    os.makedirs('./storage/trading-view-pine-editor', exist_ok=True)
    with open(path, 'w+') as outfile:
        outfile.write(tv_text)

    print('\nPine-editor output saved at: \n{}'.format(path))
