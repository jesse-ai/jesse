import os
from datetime import datetime, timedelta

import arrow
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
from adjustText import adjust_text
from matplotlib import pyplot as plt
from matplotlib.lines import Line2D
from pandas.plotting import register_matplotlib_converters

import jesse.helpers as jh
from jesse.config import config
from jesse.routes import router
from jesse.store import store


def portfolio_vs_asset_returns(enriched=False):
    register_matplotlib_converters()
    trades = store.completed_trades.trades
    # create a plot figure
    plt.figure(figsize=(26, 16))

    # daily balance
    plt.subplot(2, 1, 1)
    start_date = datetime.fromtimestamp(store.app.starting_time / 1000)
    date_list = [start_date + timedelta(days=x) for x in range(len(store.app.daily_balance))]
    plt.xlabel('date')
    plt.ylabel('balance')
    plt.title('Portfolio Daily Return')
    plt.plot(date_list, store.app.daily_balance)
    plt.grid(True)

    # price change%
    plt.subplot(2, 1, 2)
    price_dict = {}
    for r in router.routes:
        key = jh.key(r.exchange, r.symbol)
        price_dict[key] = {
            'indexes': {},
            'prices': []
        }
        dates = []
        prices = []
        candles = store.candles.get_candles(r.exchange, r.symbol, '1m')
        max_timeframe = jh.max_timeframe(config['app']['considering_timeframes'])
        pre_candles_count = jh.timeframe_to_one_minutes(max_timeframe) * 210
        for i, c in enumerate(candles):
            # do not plot prices for required_initial_candles period
            if i < pre_candles_count:
                continue

            dates.append(datetime.fromtimestamp(c[0] / 1000))
            prices.append(c[2])
            # save index of the price instead of the actual price
            price_dict[key]['indexes'][str(int(c[0]))] = len(prices) - 1

        # price => %returns
        price_returns = pd.Series(prices).pct_change(1) * 100
        cumsum_returns = np.cumsum(price_returns)
        if len(router.routes) == 1:
            plt.plot(dates, cumsum_returns, label=r.symbol, c='grey')
        else:
            plt.plot(dates, cumsum_returns, label=r.symbol)
        price_dict[key]['prices'] = cumsum_returns

    # buy and sell plots
    buy_x = []
    buy_y = []
    sell_x = []
    sell_y = []
    label_pad_box = 2
    labels = []
    for t in trades:
        key = jh.key(t.exchange, t.symbol)

        if t.type == 'long':
            buy_x.append(datetime.fromtimestamp(t.opened_at / 1000))
            sell_x.append(datetime.fromtimestamp(t.closed_at / 1000))
            # add price change%
            buy_y.append(
                price_dict[key]['prices'][price_dict[key]['indexes'][str(int(t.opened_at))]]
            )
            sell_y.append(
                price_dict[key]['prices'][price_dict[key]['indexes'][str(int(t.closed_at))]]
            )
            if enriched:
                # add label with price on open and close position
                # Opening position
                label_text = str(t.entry_price)
                label_text = label_text[0:min(len(label_text), 6)]
                labels.append(drawLabelBox(buy_x[-1], buy_y[-1], label_pad_box, 'green', label_text))
                # Closing position
                label_text = str(t.exit_price)
                label_text = label_text[0:min(len(label_text), 6)]
                label_text += "\nPNL%:" + str(t.PNL_percentage)
                labels.append(drawLabelBox(sell_x[-1], sell_y[-1], label_pad_box, 'blue', label_text))
        elif t.type == 'short':
            buy_x.append(datetime.fromtimestamp(t.closed_at / 1000))
            sell_x.append(datetime.fromtimestamp(t.opened_at / 1000))
            # add price change%
            buy_y.append(
                price_dict[key]['prices'][price_dict[key]['indexes'][str(int(t.closed_at))]]
            )
            sell_y.append(
                price_dict[key]['prices'][price_dict[key]['indexes'][str(int(t.opened_at))]]
            )
            if enriched:
                # add label with price on open and close position
                # Opening position
                label_text = str(t.entry_price)
                label_text = label_text[0:min(len(label_text), 6)]
                labels.append(drawLabelBox(sell_x[-1], sell_y[-1], label_pad_box, 'red', label_text))
                # Closing position
                label_text = str(t.exit_price)
                label_text = label_text[0:min(len(label_text), 6)]
                label_text += "\nPNL%:" + str(t.PNL_percentage)
                labels.append(drawLabelBox(buy_x[-1], buy_y[-1], label_pad_box, 'purple', label_text))

    plt.grid(True)
    plt.plot(buy_x, buy_y, '.', color='green')
    plt.plot(sell_x, sell_y, '.', color='red')

    plt.xlabel('date')
    plt.ylabel('price change %')
    plt.title('Asset Daily Return')

    long_dot_patch = Line2D([0], [0], marker='o', color='w', label='Buy',
                            markerfacecolor='green', markersize=9)
    short_dot_patch = Line2D([0], [0], marker='o', color='w', label='Sell',
                             markerfacecolor='red', markersize=9)
    legend_handles = [long_dot_patch, short_dot_patch]
    if enriched:
        adjust_text(labels, arrowprops=dict(arrowstyle='-', color='black', lw=0.5),
                    autoalign=False, only_move={'points': 'y', 'text': 'y', 'objects': 'y'},
                    ha='center',
                    expand_text=(1, 1.7),  # We want them to be quite compact, so reducing expansion makes sense
                    force_text=(0, 1)
                    # With default forces it takes a very long time to converge, but higher values still produce very nice output
                    )
        green_label_patch = mpatches.Patch(color='green', alpha=0.3, label='Long/Buy')
        red_label_patch = mpatches.Patch(color='red', alpha=0.3, label='Short/Sell')
        blue_label_patch = mpatches.Patch(color='blue', alpha=0.3, label='Long/Buy Close')
        purple_label_patch = mpatches.Patch(color='purple', alpha=0.3, label='Short/Sell Close')
        legend_handles += [green_label_patch, red_label_patch, blue_label_patch, purple_label_patch]

    additional_legend = plt.legend(handles=legend_handles, loc='lower left')

    plt.gca().add_artist(additional_legend)
    plt.legend(loc='upper left')  # default (main lines)

    # store final result
    mode = config['app']['trading_mode']
    if mode == 'backtest':
        mode = 'BT'
    if mode == 'livetrade':
        mode = 'LT'
    if mode == 'papertrade':
        mode = 'PT'

    # make sure directories exist
    os.makedirs('./storage/charts', exist_ok=True)
    file_path = 'storage/charts/{}-{}.png'.format(
        mode, str(arrow.utcnow())[0:19]
    ).replace(":", "-")
    plt.savefig(file_path)
    print(
        'Chart output saved at:\n{}'.format(file_path)
    )


def drawLabelBox(x, y, label_pad_box, colorboxbg, text):
    textstr = str(text)
    return plt.text(x, y, textstr, style='italic', fontsize='8',
                    bbox={'facecolor': colorboxbg, 'alpha': 0.3, 'pad': label_pad_box})
