import os

import jesse.helpers as jh
from jesse.store import store


def tradingview_logs(study_name: str) -> str:
    starting_balance = sum(
        store.exchanges.storage[e].starting_assets[jh.app_currency()]
        for e in store.exchanges.storage
    )

    tv_text = f'//@version=4\nstrategy("{study_name}", overlay=true, initial_capital={starting_balance}, commission_type=strategy.commission.percent, commission_value=0.2)\n'
    for i, t in enumerate(store.completed_trades.trades[::-1][:]):
        tv_text += '\n'
        for j, o in enumerate(t.orders):
            when = f"time_close == {int(o.executed_at)}"
            if int(o.executed_at) % (jh.timeframe_to_one_minutes(t.timeframe) * 60_000) != 0:
                when = f"time_close >= {int(o.executed_at)} and time_close - {int(o.executed_at) + jh.timeframe_to_one_minutes(t.timeframe) * 60_000} < {jh.timeframe_to_one_minutes(t.timeframe) * 60_000}"
            if j == len(t.orders) - 1:
                tv_text += f'strategy.close("{i}", when = {when})\n'
            else:
                tv_text += f'strategy.order("{i}", {1 if t.type == "long" else 0}, {abs(o.qty)}, {o.price}, when = {when})\n'

    path = f'storage/trading-view-pine-editor/{jh.get_session_id()}.txt'.replace(":", "-")
    os.makedirs('./storage/trading-view-pine-editor', exist_ok=True)
    with open(path, 'w+') as outfile:
        outfile.write(tv_text)

    return path
