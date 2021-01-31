import os
import sys

import jesse.helpers as jh
from jesse.store import store

def add_label_with_text(order, text_to_add, time, operation) -> str:
    y_text = 'low'
    text_color = 'color.purple'
    label_color = 'color.purple'
    label_text = ''
    orderStr = str(order)
    label_var_name = 'label_'+operation+orderStr
    enable_label_order = 'enable_label_'+operation+orderStr
    label_size = 'size.tiny'
    label_style = 'label.style_circle'

    if operation == 'buy':
        y_text = 'low'
        text_color = 'color.blue'
        label_color = 'color.blue'
        label_size = 'size.small'
        label_style = 'label.style_diamond'

    label_text = ('Order ' + orderStr + ': ( '+operation+' )\n').encode("unicode_escape").decode("utf-8")
    if text_to_add != '':
        label_text += text_to_add.encode("unicode_escape").decode("utf-8")

    text = 'var enable_label_'+operation+orderStr+' = false\n'
    text += 'if (enable_label_all == true or '+enable_label_order+' == true)\n'
    # 'text="'+label_text+'", ' \
    text += '    var '+label_var_name+' = label.new(x='+str(int(time))+', y='+y_text+', xloc=xloc.bar_time, tooltip="'+label_text+'", ' \
      'style='+label_style+', textalign=text.align_left, textcolor='+text_color+', size='+label_size+', color='+label_color+')\n'
    return text

def tradingview_logs(study_name=None, mode=None, now=None):
    """

    :param study_name:
    :param mode:
    :param now:
    """

    # Tradingview debug
    tv_debug = False
    label_with_text = ''
    study_name_tv = study_name
    for i, arg in enumerate(sys.argv):
        if "tradingview-debug" in arg:
            tv_debug = True
    if True == tv_debug:
        study_name_tv = study_name + '-debug'

    tv_text = '//@version=4\nstrategy("{}", overlay=true, initial_capital=10000, commission_type=strategy.commission.percent, commission_value=0.2)\n'.format(
        study_name_tv)
    tv_text_debug = tv_text
    tv_text_debug += 'var enable_label_all = true\n'

    for i, t in enumerate(store.completed_trades.trades[::-1][:]):
        tv_text += '\n'
        tv_text_debug += '\n'
        for j, o in enumerate(t.orders):
            when = "time_close == {}".format(int(o.executed_at))
            if int(o.executed_at) % (jh.timeframe_to_one_minutes(t.timeframe) * 60_000) != 0:
                when = "time_close >= {} and time_close - {} < {}" \
                    .format(int(o.executed_at),
                            int(o.executed_at) + jh.timeframe_to_one_minutes(t.timeframe) * 60_000,
                            jh.timeframe_to_one_minutes(t.timeframe) * 60_000)

            if j == len(t.orders) - 1:
                tv_text += 'strategy.close("{}", when = {})\n'.format(i, when)
                if True == tv_debug:
                    label_with_text = add_label_with_text(i, o.description, o.executed_at, 'close')
            else:
                tv_text += 'strategy.order("{}", {}, {}, {}, when = {})\n'.format(
                    i, 1 if t.type == 'long' else 0, abs(o.qty), o.price, when
                )
                if True == tv_debug:
                    label_with_text = add_label_with_text(i, o.description, o.executed_at, 'buy')
            if True == tv_debug:
                tv_text_debug += label_with_text

    # TradinvView orders file
    path = 'storage/trading-view-pine-editor/{}-{}.txt'.format(mode, now).replace(":", "-")
    os.makedirs('./storage/trading-view-pine-editor', exist_ok=True)
    with open(path, 'w+') as outfile:
        outfile.write(tv_text)
    print('\nPine-editor output saved at: \n{}'.format(path))

    # Tradingview orders file with debugging description
    if True == tv_debug:
        path_debug = 'storage/trading-view-pine-editor/{}-{}-debug.txt'.format(mode, now).replace(":", "-")
        with open(path_debug, 'w+') as outfile_debug:
            outfile_debug.write(tv_text_debug)
        print('\nPine-editor Tradingview-debug output saved at: \n{}'.format(path_debug))

