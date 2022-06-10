import os
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
from pandas.plotting import register_matplotlib_converters

import jesse.helpers as jh
from jesse.config import config
from jesse.routes import router
from jesse.store import store


def equity_curve() -> list:
    if store.completed_trades.count == 0:
        return None

    start_date = datetime.fromtimestamp(store.app.starting_time / 1000)
    date_list = [start_date + timedelta(days=x) for x in range(len(store.app.daily_balance))]
    daily_balance = store.app.daily_balance

    return [{
        'timestamp': date.timestamp(),
        'balance': balance
    } for date, balance in zip(date_list, daily_balance)]


def portfolio_vs_asset_returns(study_name: str = None) -> str:
    if jh.is_unit_testing():
        return 'charts'

    if store.completed_trades.count == 0:
        return None

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
    if study_name:
        plt.title(f'Portfolio Daily Return - {study_name}')
    else:
        plt.title('Portfolio Daily Return')
    plt.plot(date_list, store.app.daily_balance)

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
        pre_candles_count = jh.timeframe_to_one_minutes(max_timeframe) * jh.get_config(
            'env.data.warmup_candles_num', 210
        )
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
    for index, t in enumerate(trades):
        key = jh.key(t.exchange, t.symbol)

        # dirty fix for an issue with last trade being an open trade at the end of backtest
        if index == len(trades) - 1 and store.app.total_open_trades > 0:
            continue

        if t.type == 'long':
            # Buy
            if str(int(t.opened_at)) in price_dict[key]['indexes']:
                # add price change%
                buy_y.append(
                    price_dict[key]['prices'][price_dict[key]['indexes'][str(int(t.opened_at))]]
                )
                # add datetime
                buy_x.append(datetime.fromtimestamp(t.opened_at / 1000))

            # Sell: only generate data point if this trade wasn't after the last candle (open position at end)
            if str(int(t.closed_at)) in price_dict[key]['indexes']:
                # add price change%
                sell_y.append(
                    price_dict[key]['prices'][price_dict[key]['indexes'][str(int(t.closed_at))]]
                )
                # add datetime
                sell_x.append(datetime.fromtimestamp(t.closed_at / 1000))

        elif t.type == 'short':
            # Buy: only generate data point if this trade wasn't after the last candle (open position at end)
            if str(int(t.closed_at)) in price_dict[key]['indexes']:
                # add price change%
                buy_y.append(
                    price_dict[key]['prices'][price_dict[key]['indexes'][str(int(t.closed_at))]]
                )
                # add datetime
                buy_x.append(datetime.fromtimestamp(t.closed_at / 1000))

            # Sell
            if str(int(t.opened_at)) in price_dict[key]['indexes']:
                # add price change%
                sell_y.append(
                    price_dict[key]['prices'][price_dict[key]['indexes'][str(int(t.opened_at))]]
                )
                # add datetime
                sell_x.append(datetime.fromtimestamp(t.opened_at / 1000))

    plt.plot(buy_x, np.array(buy_y) * 0.99, '^', color='blue', markersize=7)
    plt.plot(sell_x, np.array(sell_y) * 1.01, 'v', color='red', markersize=7)

    plt.xlabel('date')
    plt.ylabel('price change %')
    plt.title('Asset Daily Return')
    plt.legend(loc='upper left')

    # store final result
    # make sure directories exist
    os.makedirs('./storage/charts', exist_ok=True)
    file_path = f'storage/charts/{jh.get_session_id()}.png'
    plt.savefig(file_path)

    return file_path
