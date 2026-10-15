from jesse.enums import order_statuses, order_types
from jesse.store import store
from jesse.strategies import Strategy


class TestProtectiveOrdersAcrossTradingModes(Strategy):
    """
    Verify that a stop closes the trade and cancels its take-profit sibling.

    The deterministic downtrend opens at 100, crosses the stop at 98, and can
    never reach the sibling take-profit at 110. Those prices make which order
    should execute—and which should be canceled—unambiguous.
    """

    def before(self) -> None:
        if self.index == 0:
            self.vars['closed_by_stop'] = False
        elif self.price == 99:
            # Protective assignments made in on_open_position are submitted
            # after that callback returns and are active by the next candle.
            assert len(self.active_exit_orders) == 2
            assert {exit_order.type for exit_order in self.active_exit_orders} == {
                order_types.LIMIT,
                order_types.STOP,
            }
            self.vars['take_profit_order'] = next(
                exit_order for exit_order in self.active_exit_orders if exit_order.is_take_profit
            )

    def before_terminate(self) -> None:
        assert self.vars['closed_by_stop'] is True
        assert store.app.total_liquidations == 0

    def should_long(self) -> bool:
        return self.price == 100

    def go_long(self) -> None:
        self.buy = 2, self.price

    def on_open_position(self, order) -> None:
        exit_qty = self.position.qty
        self.stop_loss = exit_qty, 98
        self.take_profit = exit_qty, 110

    def on_close_position(self, order, closed_trade) -> None:
        assert order.type == order_types.STOP
        assert order.is_stop_loss is True
        assert order.price == 98
        assert self.position.qty == 0
        assert self.active_exit_orders == []

        # Canceled orders leave the active order store, so retain the submitted
        # object to verify that sibling cancellation changed its status.
        assert self.vars['take_profit_order'].status == order_statuses.CANCELED

        assert closed_trade.type == 'long'
        assert closed_trade.entry_price == 100
        assert closed_trade.exit_price == 98
        assert closed_trade.qty == 2

        exchange = store.exchanges.get_exchange(self.exchange)
        if self.is_spot_trading:
            # As with the profitable lifecycle contract, the buy fee is paid in
            # BTC while the stop's sell fee is paid in USDT: the engine sells
            # the remaining 1.998 BTC at 98 with a 0.1% fee.
            assert exchange.assets['BTC'] == 0
            assert round(exchange.wallet_balance, 8) == 9_995.608196
            assert round(closed_trade.fee, 8) == 0.395804
            assert round(closed_trade.pnl, 8) == -4.395804
        else:
            # Futures charges 0.1% in USDT on the 200 entry notional and the
            # 196 exit notional, in addition to the four-dollar trading loss.
            assert round(exchange.wallet_balance, 8) == 9_995.604
            assert round(closed_trade.fee, 8) == 0.396
            assert round(closed_trade.pnl, 8) == round(exchange.wallet_balance - 10_000, 8)

        self.vars['closed_by_stop'] = True
