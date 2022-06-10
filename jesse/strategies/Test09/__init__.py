from jesse.strategies import Strategy


# test_stats_for_a_strategy_without_any_trades
class Test09(Strategy):
    def should_long(self):
        return False

    def should_short(self):
        return False

    def go_long(self):
        pass

    def go_short(self):
        pass

    def should_cancel_entry(self):
        return False

    def filters(self):
        return []
