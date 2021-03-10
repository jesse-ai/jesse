class CompletedTrades:
    def __init__(self) -> None:
        self.trades = []

    def add_trade(self, trade) -> None:
        self.trades.append(trade)

    @property
    def count(self) -> int:
        return len(self.trades)
