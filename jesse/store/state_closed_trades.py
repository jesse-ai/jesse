from jesse.models import ClosedTrade
import jesse.helpers as jh


class ClosedTrades:
    def __init__(self) -> None:
        self.trades = []
        self.tempt_trades = {}
        # the trade each route's latest closure recorded, consumed by on_close_position
        self.just_closed = {}

    def _get_current_trade(self, exchange: str, symbol: str) -> ClosedTrade:
        key = jh.key(exchange, symbol)
        # if already exists, return it
        if key in self.tempt_trades:
            t: ClosedTrade = self.tempt_trades[key]
            # set the trade.id if not generated already
            if not t.id:
                t.id = jh.generate_unique_id()
            return t
        # else, create a new trade, store it, and return it
        t = ClosedTrade()
        t.id = jh.generate_unique_id()
        self.tempt_trades[key] = t
        return t

    def _reset_current_trade(self, exchange: str, symbol: str) -> None:
        key = jh.key(exchange, symbol)
        self.tempt_trades[key] = ClosedTrade()

    def record_closure(self, trade: ClosedTrade) -> None:
        """Correlate the finalized trade with this route's close callback."""
        self.just_closed[jh.key(trade.exchange, trade.symbol)] = trade

    def pop_closure(self, exchange: str, symbol: str) -> ClosedTrade | None:
        """Consume the closure once so a later callback cannot reuse a stale trade."""
        return self.just_closed.pop(jh.key(exchange, symbol), None)

    @property
    def count(self) -> int:
        return len(self.trades)
