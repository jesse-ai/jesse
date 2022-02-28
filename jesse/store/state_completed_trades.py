import numpy as np

from jesse.models import Position, CompletedTrade, Order
import jesse.helpers as jh
from jesse.models.utils import store_completed_trade_into_db
from jesse.enums import sides


class CompletedTrades:
    def __init__(self) -> None:
        self.trades = []
        self.tempt_trades = {}

    def _get_current_trade(self, exchange: str, symbol: str) -> CompletedTrade:
        key = jh.key(exchange, symbol)
        # if already exists, return it
        if key in self.tempt_trades:
            t: CompletedTrade = self.tempt_trades[key]
            # set the trade.id if not generated already
            if not t.id:
                t.id = jh.generate_unique_id()
            return t
        # else, create a new trade, store it, and return it
        t = CompletedTrade()
        t.id = jh.generate_unique_id()
        self.tempt_trades[key] = t
        return t

    def _reset_current_trade(self, exchange: str, symbol: str) -> None:
        key = jh.key(exchange, symbol)
        self.tempt_trades[key] = CompletedTrade()

    def add_executed_order(self, executed_order: Order) -> None:
        t = self._get_current_trade(executed_order.exchange, executed_order.symbol)
        executed_order.trade_id = t.id
        t.orders.append(executed_order)
        if executed_order.side == sides.BUY:
            t.buy_orders.append(np.array([abs(executed_order.qty), executed_order.price]))
        elif executed_order.side == sides.SELL:
            t.sell_orders.append(np.array([abs(executed_order.qty), executed_order.price]))
        else:
            raise Exception("Invalid order side")

    def open_trade(self, position: Position) -> None:
        t = self._get_current_trade(position.exchange_name, position.symbol)
        t.opened_at = position.opened_at
        t.leverage = position.leverage
        try:
            t.timeframe = position.strategy.timeframe
            t.strategy_name = position.strategy.name
        except AttributeError:
            if not jh.is_unit_testing():
                raise
            t.timeframe = None
            t.strategy_name = None
        t.exchange = position.exchange_name
        t.symbol = position.symbol
        t.type = position.type

    def close_trade(self, position: Position) -> None:
        t = self._get_current_trade(position.exchange_name, position.symbol)
        t.closed_at = position.closed_at
        try:
            position.strategy.trades_count += 1
        except AttributeError:
            if not jh.is_unit_testing():
                raise

        if jh.is_livetrading():
            store_completed_trade_into_db(t)
        # store the trade into the list
        self.trades.append(t)
        # at the end, reset the trade variable
        self._reset_current_trade(position.exchange_name, position.symbol)

    # TODO: to detect initially received orders from the exchange in live mode:
    # position qty increase from 0: OPEN
    # position qty becoming 0: CLOSE
    # position qty increasing in size: INCREASE
    # position qty decreasing in size: REDUCE

    @property
    def count(self) -> int:
        return len(self.trades)
