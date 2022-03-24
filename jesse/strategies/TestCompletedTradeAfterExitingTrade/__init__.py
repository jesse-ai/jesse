import jesse.helpers as jh
from jesse.strategies import Strategy


class TestCompletedTradeAfterExitingTrade(Strategy):
    def should_long(self) -> bool:
        return self.price == 10

    def should_short(self) -> bool:
        return False

    def go_long(self):
        self.buy = 10, self.price
        self.take_profit = 10, 12
        self.stop_loss = 10, 5

    def go_short(self):
        pass

    def should_cancel(self):
        return False

    def on_close_position(self, order):
        assert self.trades_count == 1

        trade = self.trades[0]

        assert jh.is_valid_uuid(trade.id) is True
        assert trade.strategy_name == 'TestCompletedTradeAfterExitingTrade'
        assert trade.symbol == 'BTC-USDT'
        assert trade.exchange == 'Sandbox'
        assert trade.type == 'long'
        assert trade.timeframe == '1m'
        assert trade.entry_price == 10
        assert trade.exit_price == 12
        assert trade.qty == 10
        assert trade.opened_at == 1609459800000.0
        assert trade.closed_at == 1609459920000.0
        assert trade.leverage == 2

        # assert all orders have their trade_id set
        orders = trade.orders
        assert len(orders) == 2
        for o in orders:
            if not o.is_canceled:
                assert o.trade_id == trade.id
