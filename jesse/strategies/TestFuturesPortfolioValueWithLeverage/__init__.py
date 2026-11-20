from jesse.strategies import Strategy


class TestFuturesPortfolioValueWithLeverage(Strategy):
    def before(self) -> None:
        if self.price == 20:
            assert self.leverage == 2
            # 1 BTC bought at 10 is up 10, whatever the leverage
            assert self.position.pnl == 10
            assert self.portfolio_value == 10_000 + 10

        if self.price == 21:
            # closing at 20 realized exactly that profit
            assert self.position.is_close
            assert self.balance == 10_000 + 10
            assert self.portfolio_value == 10_000 + 10

    def should_long(self) -> bool:
        return self.price == 10

    def go_long(self) -> None:
        self.buy = 1, self.price

    def update_position(self) -> None:
        if self.price == 20:
            self.liquidate()

    def should_cancel_entry(self):
        return False
