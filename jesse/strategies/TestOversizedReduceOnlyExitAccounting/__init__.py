from jesse.strategies import Strategy
from jesse.store import store


class TestOversizedReduceOnlyExitAccounting(Strategy):
    """
    Reproduces the oversized reduce_only exit bug: when a reduce_only order's stated qty
    exceeds the remaining position, the engine caps the actual fill but must account for
    the *capped* qty (not the stated qty) in both the exit_price VWAP and the fee.

    Down-trend prices walk 100 -> 11. We open long at 100 with TWO stop-loss tiers that
    intentionally over-sum the position (1 + 2 = 3 > entry qty 2). tier1 (@90) reduces the
    position to 1; when tier2 (@80, stated qty 2) later fires, reduce_only caps the actual
    fill to the remaining 1.
    """

    def should_long(self):
        return self.price == 100

    def go_long(self):
        if self.price == 100:
            self.buy = 2, self.price

    def on_open_position(self, order):
        # stated qtys sum to 3 while the position is only 2 -> the @80 tier is oversized
        # once the @90 tier has reduced the position.
        self.stop_loss = [(1, 90), (2, 80)]

    def on_close_position(self, order, closed_trade) -> None:
        assert closed_trade.type == 'long'
        assert closed_trade.entry_price == 100
        assert closed_trade.qty == 2

        # exit VWAP must weight the second leg by the ACTUAL filled 1, not the stated 2:
        #   correct: (1*90 + 1*80) / (1 + 1) = 85
        #   buggy:   (1*90 + 2*80) / (1 + 2) = 83.333...
        assert round(closed_trade.exit_price, 8) == 85

        # headline invariant: per-trade pnl must equal the real wallet balance change.
        # this fails if either the exit_price VWAP or the fee is computed on the stated qty.
        e = store.exchanges.get_exchange(self.exchange)
        wallet_delta = e.wallet_balance - 10_000
        assert round(closed_trade.pnl, 8) == round(wallet_delta, 8)
