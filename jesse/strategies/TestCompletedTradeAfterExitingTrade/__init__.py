import jesse.helpers as jh
from jesse.models import Order
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

    def on_take_profit(self, order: Order):
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
        assert trade.take_profit_at == 12
        assert trade.stop_loss_at == 5
        assert trade.qty == 10
        assert trade.opened_at == 1552309906171.0
        assert trade.closed_at == 1552310026171.0
        assert trade.leverage == 2

        # assert all orders have their trade_id set
        from jesse.store import store
        orders = store.orders.get_orders(trade.exchange, trade.symbol)
        assert len(orders) == 3
        for o in orders:
            if not o.is_canceled:
                assert o.trade_id == trade.id
