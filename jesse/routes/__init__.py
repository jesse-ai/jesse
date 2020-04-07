from jesse.models import Route


class RouterClass:
    def __init__(self):
        self.routes = []
        self.extra_candles = []
        self.market_data = []

    def set_routes(self, routes):
        self.routes = []
        for r in routes:
            self.routes.append(Route(*r))

    def set_market_data(self, routes):
        self.market_data = []
        for r in routes:
            self.market_data.append(Route(*r))

    def set_extra_candles(self, extra_candles):
        self.extra_candles = extra_candles


router = RouterClass()
