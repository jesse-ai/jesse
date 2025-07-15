from jesse.strategies import Strategy


class TestDataRoutes2(Strategy):
    def before(self) -> None:
        if self.index == 0 or self.index == 10:
            assert self.data_routes[0].symbol == 'BTC-USDT'
            assert self.data_routes[0].timeframe == '5m'
            assert self.data_routes[0].strategy == None
            assert self.data_routes[1].symbol == 'ETH-USDT'
            assert self.data_routes[1].timeframe == '15m'
            assert self.data_routes[1].strategy == None

    def should_long(self):
        return False

    def go_long(self):
        pass

    def should_cancel_entry(self):
        return False
