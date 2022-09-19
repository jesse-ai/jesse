from jesse.strategies import Strategy
import jesse.helpers as jh
from jesse import utils


class TestDailyBalancesProperty(Strategy):
    def should_long(self) -> bool:
        return False

    def go_long(self) -> None:
        pass

    def should_cancel_entry(self):
        return False

    def before_terminate(self):
        assert len(self.daily_balances) == 10
        for d in self.daily_balances:
            assert d == 10_000
