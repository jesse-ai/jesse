import sys
from typing import List, Any

import jesse.helpers as jh
from jesse import exceptions
from jesse.enums import timeframes
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

    def initiate(self, routes: list, extra_routes: list):
        self.set_routes(routes)
        self.set_extra_candles(extra_routes)
        from jesse.store import store
        store.reset(force_install_routes=jh.is_unit_testing())

    def set_routes(self, routes: List[Any]) -> None:
        self._reset()

        self.routes = []

        for r in routes:
            # validate strategy
            strategy_name = r["strategy"]
            if jh.is_unit_testing():
                exists = jh.file_exists(f"{sys.path[0]}/jesse/strategies/{strategy_name}/__init__.py")
            else:
                exists = jh.file_exists(f'strategies/{strategy_name}/__init__.py')
            if not exists:
                raise exceptions.InvalidRoutes(
                    f'A strategy with the name of "{strategy_name}" could not be found.')

            self.routes.append(Route(r["exchange"], r["symbol"], r["timeframe"], r["strategy"], None))

    def set_market_data(self, routes: List[Any]) -> None:
        self.market_data = []
        for r in routes:
            self.market_data.append(Route(*r))

    def set_extra_candles(self, extra_candles) -> None:
        self.extra_candles = extra_candles


router: RouterClass = RouterClass()
