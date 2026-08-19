import jesse.helpers as jh
from jesse import utils
from jesse.config import config
from jesse.enums import order_types
from jesse.store import store
from jesse.strategies import Strategy


class TestLongLifecycleAcrossTradingModes(Strategy):
    """
    Lock down one complete long lifecycle across spot and futures modes.

    The deterministic uptrend opens at 10, then closes equal halves at 12 and
    14. That gives an unambiguous exit VWAP of 13 while exercising both the
    reduced-position and closed-position callbacks.
    """

    def before(self) -> None:
        if self.index == 0:
            self.vars['opened'] = False
            self.vars['reduced'] = False
            self.vars['closed'] = False

    def before_terminate(self) -> None:
        assert self.vars['opened'] is True
        assert self.vars['reduced'] is True
        assert self.vars['closed'] is True
        assert len(store.closed_trades.trades) == 1
        assert store.app.total_open_trades == 0
        assert store.app.total_liquidations == 0

    def should_long(self) -> bool:
        return self.price == 10

    def go_long(self) -> None:
        self.buy = 2, self.price

    def on_open_position(self, order) -> None:
        assert order.type == order_types.MARKET
        assert order.qty == 2
        assert self.position.entry_price == 10
        expected_mode = (
            'spot'
            if self.is_spot_trading
            else config['env']['exchanges'][self.exchange]['futures_leverage_mode']
        )
        assert self.position.mode == expected_mode
        assert self.position.leverage == (1 if self.is_spot_trading else 2)

        # Spot deducts the entry fee from the acquired base asset, while futures
        # keeps the submitted quantity and charges fees against the quote wallet.
        expected_qty = 1.998 if self.is_spot_trading else 2
        assert self.position.qty == expected_qty

        first_exit_qty = expected_qty / 2
        second_exit_qty = utils.subtract_floats(expected_qty, first_exit_qty)
        self.vars['second_exit_qty'] = second_exit_qty
        self.take_profit = [
            (first_exit_qty, 12),
            (second_exit_qty, 14),
        ]
        self.vars['opened'] = True

    def on_reduced_position(self, order) -> None:
        assert order.type == order_types.LIMIT
        assert order.price == 12
        assert self.position.qty == self.vars['second_exit_qty']
        self.vars['reduced'] = True

    def on_close_position(self, order, closed_trade) -> None:
        assert order.type == order_types.LIMIT
        assert order.price == 14
        assert self.position.qty == 0

        assert closed_trade.type == 'long'
        assert closed_trade.entry_price == 10
        assert closed_trade.exit_price == 13
        assert closed_trade.qty == 2
        assert closed_trade.timeframe == self.timeframe
        assert closed_trade.exchange == self.exchange
        assert closed_trade.symbol == self.symbol
        assert closed_trade.leverage == (1 if self.is_spot_trading else 2)

        exchange = store.exchanges.get_exchange(self.exchange)
        if self.is_spot_trading:
            # The spot buy fee reduces BTC before the two sell fees reduce USDT.
            # This makes the quote-wallet delta intentionally differ from the
            # trade model's quote-denominated fee calculation: quote proceeds
            # are 0.999 BTC at 12 and 14, each charged a 0.1% sell fee.
            assert jh.base_asset(self.symbol) == 'BTC'
            assert exchange.assets['BTC'] == 0
            assert round(exchange.wallet_balance, 8) == 10_005.948026
            assert round(closed_trade.fee, 8) == 0.045974
            assert round(closed_trade.pnl, 8) == 5.954026
        else:
            # Futures charges 0.1% in USDT on the 20 entry notional and the
            # two exit notionals of 12 and 14.
            assert round(exchange.wallet_balance, 8) == 10_005.954
            assert round(closed_trade.fee, 8) == 0.046
            assert round(closed_trade.pnl, 8) == round(exchange.wallet_balance - 10_000, 8)

        self.vars['closed'] = True
