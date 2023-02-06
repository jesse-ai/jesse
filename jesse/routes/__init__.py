import sys
from typing import List, Any

import jesse.helpers as jh
from jesse import exceptions
from jesse.services import logger
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

    @property
    def formatted_routes(self) -> list:
        """
        Example:
        [{'exchange': 'Binance', 'strategy': 'A1', 'symbol': 'BTC-USDT', 'timeframe': '1m'}]
        """
        return [
            {
                'exchange': r.exchange,
                'symbol': r.symbol,
                'timeframe': r.timeframe,
                'strategy': r.strategy_name,
            }
            for r in self.routes
        ]

    @property
    def formatted_extra_routes(self) -> list:
        """
        Example:
        [{'exchange': 'Binance', 'symbol': 'BTC-USD', 'timeframe': '3m'}]
        """
        return [{
            'exchange': r['exchange'],
            'symbol': r['symbol'],
            'timeframe': r['timeframe']
        } for r in self.extra_candles]

    @property
    def all_formatted_routes(self) -> list:
        return self.formatted_routes + self.formatted_extra_routes

    def initiate(self, routes: list, extra_routes: list = None):
        if extra_routes is None:
            extra_routes = []
        self.set_routes(routes)
        self.set_extra_candles(extra_routes)
        from jesse.store import store
        store.reset(force_install_routes=jh.is_unit_testing())

    def set_routes(self, routes: List[Any]) -> None:
        self._reset()

        self.routes = []

        for r in routes:
            # validate strategy that the strategy file exists (if sent as a string)
            if isinstance(r["strategy"], str):
                strategy_name = r["strategy"]
                if jh.is_unit_testing():
                    path = sys.path[0]
                    # live plugin
                    if path.endswith('jesse-live'):
                        strategies_dir = f'{sys.path[0]}/tests/strategies'
                    # main framework
                    else:
                        strategies_dir = f'{sys.path[0]}/jesse/strategies'
                    exists = jh.file_exists(f"{strategies_dir}/{strategy_name}/__init__.py")
                else:
                    exists = jh.file_exists(f'strategies/{strategy_name}/__init__.py')
            else:
                exists = True

            if not exists and isinstance(r["strategy"], str):
                raise exceptions.InvalidRoutes(
                    f'A strategy with the name of "{r["strategy"]}" could not be found.')

            self.routes.append(Route(r["exchange"], r["symbol"], r["timeframe"], r["strategy"], None))

    def set_market_data(self, routes: List[Any]) -> None:
        self.market_data = []
        for r in routes:
            self.market_data.append(Route(*r))

    def set_extra_candles(self, extra_candles: list) -> None:
        self.extra_candles = extra_candles


router: RouterClass = RouterClass()
