class CompletedTrades:
    """

    """
    def __init__(self):
        self.trades = []

    def add_trade(self, trade):
        """

        :param trade:
        """
        self.trades.append(trade)

    @property
    def count(self):
        return len(self.trades)
