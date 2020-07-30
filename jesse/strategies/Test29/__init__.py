from jesse.strategies import Strategy


# test_on_route_increased_position_and_on_route_reduced_position_and_strategy_vars part 1 - BTCUSD
class Test29(Strategy):
    """

    """
    def __init__(self):
        super().__init__()

        self.vars['should_short'] = False
        self.vars['should_long'] = False

    def should_long(self):
        return self.vars['should_long']

    def should_short(self):
        return self.vars['should_short']

    def go_long(self):
        self.buy = 1, self.price
        self.take_profit = 1, self.price + 10

    def go_short(self):
        self.sell = 1, self.price
        self.stop_loss = 1, self.price + 10

    def on_route_increased_position(self, strategy):
        """

        :param strategy:
        """
        # setting it to True means we'll open a position on NEXT candle
        self.vars['should_long'] = True

    def on_route_reduced_position(self, strategy):
        """

        :param strategy:
        """
        # setting it to True means we'll open a position on NEXT candle
        self.vars['should_short'] = True

    def should_cancel(self):
        return False

    def on_take_profit(self):
        self.vars['should_long'] = False
        self.vars['should_short'] = False

    def on_stop_loss(self):
        self.vars['should_long'] = False
        self.vars['should_short'] = False
