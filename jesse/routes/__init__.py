import sys
from typing import List, Any

import jesse.helpers as jh
from jesse import exceptions
from jesse.models import Route


class RouterClass:
    def __init__(self) -> None:
        self.routes = []
        self.extra_candles = []
        self.market_data = []

    def _reset(self) -> None:
        self.routes = []
        self.extra_candles = []
        self.market_data = []

    def set_routes(self, routes: List[Any]) -> None:
        self._reset()

        self.routes = []

        for r in routes:
            # validate strategy
            strategy_name = r[3]
            if jh.is_unit_testing():
                exists = jh.file_exists(sys.path[0] + '/jesse/strategies/{}/__init__.py'.format(strategy_name))
            else:
                exists = jh.file_exists('strategies/{}/__init__.py'.format(strategy_name))

            if not exists:
                raise exceptions.InvalidRoutes(
                    'A strategy with the name of "{}" could not be found.'.format(r[3]))

            # validate timeframe
            timeframe = r[2]
            if timeframe not in ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '3h', '4h', '6h', '8h', '1D']:
                raise exceptions.InvalidRoutes(
                    'Timeframe "{}" is invalid. Supported timeframes are 1m, 3m, 5m, 15m, 30m, 1h, 2h, 3h, 4h, 6h, 8h, 1D'.format(
                        timeframe)
                )

            self.routes.append(Route(*r))

    def set_market_data(self, routes: List[Any]) -> None:
        self.market_data = []
        for r in routes:
            self.market_data.append(Route(*r))

    def set_extra_candles(self, extra_candles) -> None:
        self.extra_candles = extra_candles


router: RouterClass = RouterClass()
